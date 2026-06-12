from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.catalog_match import (
    SegmentEdge,
    SnapHit,
    gps_bearing_at,
    point_to_segment_distance_m,
)
from app.core.geo import bearing_match_deg, haversine_m


MIN_TURN_SUPPORT_POINTS = int(os.getenv("CATALOG_MATCH_MIN_TURN_SUPPORT_POINTS", "3"))
SHORT_SPUR_MAX_M = float(os.getenv("CATALOG_MATCH_SHORT_SPUR_MAX_M", "40"))
LOW_SUPPORT_MAX_POINTS = int(os.getenv("CATALOG_MATCH_LOW_SUPPORT_MAX_POINTS", "2"))
SPUR_ANGLE_MIN_DEG = float(os.getenv("CATALOG_MATCH_SPUR_ANGLE_MIN_DEG", "50"))
HEADING_HARD_DEG = float(os.getenv("CATALOG_MATCH_HEADING_HARD_DEG", "60"))


@dataclass
class CleanupStats:
    suppressed_spur_count: int = 0
    weak_turn_reassignments: int = 0
    low_support_segment_count: int = 0


@dataclass
class SegmentRun:
    segment_id: str
    run_index: int
    first_hit_idx: int
    last_hit_idx: int
    gps_point_count: int
    avg_distance_m: float
    avg_heading_delta_deg: float | None
    matched_length_m: float
    canonical_length_m: float


def same_corridor(a: SegmentEdge, b: SegmentEdge) -> bool:
    if a.osm_way_id is not None and b.osm_way_id is not None and a.osm_way_id == b.osm_way_id:
        return True
    if a.name and b.name and a.name == b.name:
        return True
    return bearing_match_deg(a.bearing_deg, b.bearing_deg) < 35.0


def build_segment_runs(
    hits: list[SnapHit | None],
    points: list[tuple[float, float]],
    edge_by_id: dict[str, SegmentEdge],
) -> list[SegmentRun]:
    runs: list[SegmentRun] = []
    run_index = 0
    idx = 0
    n = len(hits)

    while idx < n:
        hit = hits[idx]
        if not hit:
            idx += 1
            continue

        seg_id = hit.segment_id
        first_idx = idx
        distances: list[float] = []
        heading_deltas: list[float] = []
        matched_len = 0.0
        prev_hit: SnapHit | None = None

        while idx < n and hits[idx] and hits[idx].segment_id == seg_id:
            h = hits[idx]
            assert h is not None
            distances.append(h.snap_distance_m)
            gps_bearing, reliable = gps_bearing_at(points, h.order)
            edge = edge_by_id.get(seg_id)
            if gps_bearing is not None and reliable and edge is not None:
                heading_deltas.append(bearing_match_deg(gps_bearing, edge.bearing_deg))
            if prev_hit is not None:
                matched_len += haversine_m(
                    prev_hit.matched_lon,
                    prev_hit.matched_lat,
                    h.matched_lon,
                    h.matched_lat,
                )
            prev_hit = h
            idx += 1

        edge = edge_by_id.get(seg_id)
        canonical = edge.length_m if edge else matched_len
        if matched_len <= 0.0 and edge is not None:
            matched_len = min(canonical, canonical)

        runs.append(
            SegmentRun(
                segment_id=seg_id,
                run_index=run_index,
                first_hit_idx=first_idx,
                last_hit_idx=idx - 1,
                gps_point_count=idx - first_idx,
                avg_distance_m=sum(distances) / len(distances) if distances else 0.0,
                avg_heading_delta_deg=(
                    sum(heading_deltas) / len(heading_deltas) if heading_deltas else None
                ),
                matched_length_m=matched_len,
                canonical_length_m=canonical,
            )
        )
        run_index += 1

    return runs


def rehit_on_segment(
    hit: SnapHit,
    segment_id: str,
    points: list[tuple[float, float]],
    edge_by_id: dict[str, SegmentEdge],
) -> SnapHit:
    edge = edge_by_id[segment_id]
    lon, lat = points[hit.order]
    dist, clon, clat = point_to_segment_distance_m(
        lon, lat,
        edge.start_lon, edge.start_lat,
        edge.end_lon, edge.end_lat,
    )
    return SnapHit(
        segment_id=segment_id,
        order=hit.order,
        snap_distance_m=dist,
        matched_lon=clon,
        matched_lat=clat,
        total_score_m=dist,
    )


def _run_heading_supports_turn(
    run_hits: list[SnapHit],
    points: list[tuple[float, float]],
    from_edge: SegmentEdge,
    to_edge: SegmentEdge,
) -> bool:
    if not run_hits:
        return False
    deltas: list[float] = []
    for hit in run_hits:
        gps_bearing, reliable = gps_bearing_at(points, hit.order)
        if gps_bearing is None or not reliable:
            continue
        deltas.append(bearing_match_deg(gps_bearing, to_edge.bearing_deg))
    if not deltas:
        return bearing_match_deg(from_edge.bearing_deg, to_edge.bearing_deg) < HEADING_HARD_DEG
    avg = sum(deltas) / len(deltas)
    return avg <= HEADING_HARD_DEG


def count_low_support_segments(
    hits: list[SnapHit | None],
    points: list[tuple[float, float]],
    edge_by_id: dict[str, SegmentEdge],
    *,
    max_points: int = LOW_SUPPORT_MAX_POINTS,
) -> int:
    runs = build_segment_runs(hits, points, edge_by_id)
    return sum(1 for run in runs if run.gps_point_count <= max_points)


def enforce_sustained_turns(
    hits: list[SnapHit | None],
    points: list[tuple[float, float]],
    edge_by_id: dict[str, SegmentEdge],
    *,
    min_support: int = MIN_TURN_SUPPORT_POINTS,
) -> tuple[list[SnapHit | None], int]:
    """Drop weak single-sample turns onto unrelated connected segments."""
    out: list[SnapHit | None] = [h for h in hits]
    reassignments = 0
    if not out:
        return out, reassignments

    corridor_seg: str | None = None
    i = 0
    while i < len(out):
        hit = out[i]
        if not hit:
            i += 1
            continue

        if corridor_seg is None:
            corridor_seg = hit.segment_id
            i += 1
            continue

        if hit.segment_id == corridor_seg:
            i += 1
            continue

        new_seg = hit.segment_id
        j = i
        while j < len(out) and out[j] and out[j].segment_id == new_seg:
            j += 1
        support_count = j - i

        prev_edge = edge_by_id.get(corridor_seg)
        new_edge = edge_by_id.get(new_seg)
        unrelated = (
            prev_edge is not None
            and new_edge is not None
            and not same_corridor(prev_edge, new_edge)
        )

        if unrelated:
            run_hits = [h for h in out[i:j] if h]
            heading_ok = (
                prev_edge is not None
                and new_edge is not None
                and _run_heading_supports_turn(run_hits, points, prev_edge, new_edge)
            )
            if support_count < min_support and not heading_ok:
                for k in range(i, j):
                    if out[k]:
                        out[k] = rehit_on_segment(out[k], corridor_seg, points, edge_by_id)
                        reassignments += 1
                i = j
                continue

        corridor_seg = new_seg
        i = j

    return out, reassignments


def _effective_run_length_m(run: SegmentRun) -> float:
    if run.matched_length_m > 0.0:
        return run.matched_length_m
    return run.canonical_length_m


def _corridor_fallback_segment(
    runs: list[SegmentRun],
    spur_idx: int,
    edge_by_id: dict[str, SegmentEdge],
) -> str | None:
    if spur_idx > 0:
        return runs[spur_idx - 1].segment_id
    if spur_idx + 1 < len(runs):
        return runs[spur_idx + 1].segment_id
    return None


def is_spur_run(
    runs: list[SegmentRun],
    index: int,
    edge_by_id: dict[str, SegmentEdge],
) -> bool:
    if index <= 0 or index >= len(runs) - 1:
        return False

    run = runs[index]
    spur_edge = edge_by_id.get(run.segment_id)
    prev_edge = edge_by_id.get(runs[index - 1].segment_id)
    next_edge = edge_by_id.get(runs[index + 1].segment_id)
    if spur_edge is None or prev_edge is None or next_edge is None:
        return False

    length_m = _effective_run_length_m(run)
    if length_m > SHORT_SPUR_MAX_M:
        return False
    if run.gps_point_count > LOW_SUPPORT_MAX_POINTS:
        return False

    if same_corridor(spur_edge, prev_edge) or same_corridor(spur_edge, next_edge):
        return False

    if not same_corridor(prev_edge, next_edge):
        return False

    turn_in = bearing_match_deg(prev_edge.bearing_deg, spur_edge.bearing_deg)
    turn_out = bearing_match_deg(spur_edge.bearing_deg, next_edge.bearing_deg)
    if turn_in < SPUR_ANGLE_MIN_DEG and turn_out < SPUR_ANGLE_MIN_DEG:
        return False

    # Out-and-back on the same segment, or notch returning to the same corridor.
    return True


def identify_spur_run_indices(
    runs: list[SegmentRun],
    edge_by_id: dict[str, SegmentEdge],
) -> set[int]:
    return {i for i in range(len(runs)) if is_spur_run(runs, i, edge_by_id)}


def apply_spur_suppression(
    hits: list[SnapHit | None],
    points: list[tuple[float, float]],
    edge_by_id: dict[str, SegmentEdge],
) -> tuple[list[SnapHit | None], int]:
    out: list[SnapHit | None] = [h for h in hits]
    suppressed = 0
    changed = True
    while changed:
        changed = False
        runs = build_segment_runs(out, points, edge_by_id)
        spur_indices = identify_spur_run_indices(runs, edge_by_id)
        if not spur_indices:
            break
        for idx in sorted(spur_indices, reverse=True):
            run = runs[idx]
            fallback = _corridor_fallback_segment(runs, idx, edge_by_id)
            if fallback is None:
                continue
            suppressed += 1
            for hit_idx in range(run.first_hit_idx, run.last_hit_idx + 1):
                if out[hit_idx]:
                    out[hit_idx] = rehit_on_segment(out[hit_idx], fallback, points, edge_by_id)
            changed = True
    return out, suppressed


def cleanup_matched_hits(
    hits: list[SnapHit | None],
    points: list[tuple[float, float]],
    edge_by_id: dict[str, SegmentEdge],
) -> tuple[list[SnapHit | None], CleanupStats]:
    """Post-match cleanup before usage rows and visualization."""
    cleaned, weak_turns = enforce_sustained_turns(hits, points, edge_by_id)
    cleaned, spurs = apply_spur_suppression(cleaned, points, edge_by_id)
    low_support = count_low_support_segments(cleaned, points, edge_by_id)
    return cleaned, CleanupStats(
        suppressed_spur_count=spurs,
        weak_turn_reassignments=weak_turns,
        low_support_segment_count=low_support,
    )
