from __future__ import annotations

import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.core.activity_geojson import coords_from_geojson
from app.core.catalog_tiles import (
    TileConfig,
    buffer_bbox_km,
    get_tile_config,
    tiles_for_coordinates,
)
from app.core.geo import bearing_deg, bearing_match_deg, compute_bbox, haversine_m
from app.db.catalog_tiles import CatalogTileRepository
from app.db.models import Activity, NetworkSegment
from app.db.repositories import SegmentRepository
from app.db.segment_usage import SegmentUsageRepository, UsageDraft


DEFAULT_SNAP_M = float(os.getenv("CATALOG_MATCH_SNAP_M", "40"))
DEFAULT_SAMPLE_M = float(os.getenv("CATALOG_MATCH_SAMPLE_M", "15"))
MIN_BEARING_LEG_M = float(os.getenv("CATALOG_MATCH_MIN_BEARING_LEG_M", "8"))
HEADING_SOFT_DEG = float(os.getenv("CATALOG_MATCH_HEADING_SOFT_DEG", "45"))
HEADING_HARD_DEG = float(os.getenv("CATALOG_MATCH_HEADING_HARD_DEG", "60"))
HEADING_SOFT_PENALTY_M = float(os.getenv("CATALOG_MATCH_HEADING_SOFT_PENALTY_M", "12"))
HEADING_HARD_PENALTY_M = float(os.getenv("CATALOG_MATCH_HEADING_HARD_PENALTY_M", "80"))
CONTINUITY_CONNECTED_M = float(os.getenv("CATALOG_MATCH_CONTINUITY_CONNECTED_M", "2"))
CONTINUITY_SAME_WAY_M = float(os.getenv("CATALOG_MATCH_CONTINUITY_SAME_WAY_M", "6"))
CONTINUITY_JUMP_M = float(os.getenv("CATALOG_MATCH_CONTINUITY_JUMP_M", "28"))
CONTINUITY_PERPENDICULAR_M = float(os.getenv("CATALOG_MATCH_CONTINUITY_PERPENDICULAR_M", "45"))


@dataclass(frozen=True)
class SegmentEdge:
    segment_id: str
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    length_m: float
    osm_way_id: int | None = None
    osm_start_node_id: int | None = None
    osm_end_node_id: int | None = None
    name: str | None = None
    bearing_deg: float = 0.0


@dataclass
class SnapHit:
    segment_id: str
    order: int
    snap_distance_m: float
    matched_lon: float
    matched_lat: float
    total_score_m: float = 0.0


@dataclass
class UsageRow:
    segment_id: str
    traversals: int
    matched_length_m: float
    first_seen_order: int
    last_seen_order: int
    confidence: float


@dataclass
class CatalogMatchResult:
    activity_id: str
    status: str
    segment_count: int
    points_sampled: int
    points_matched: int
    points_unmatched: int
    required_tiles: int
    ready_tiles: int
    missing_tiles: list[str] = field(default_factory=list)
    not_ready_tiles: list[str] = field(default_factory=list)
    match_confidence: float | None = None
    error: str | None = None
    usage: list[UsageRow] = field(default_factory=list)
    segment_sequence: list[str] = field(default_factory=list)
    matched_coords: list[list[float]] = field(default_factory=list)


def point_to_segment_distance_m(
    lon: float,
    lat: float,
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
) -> tuple[float, float, float]:
    """Return (distance_m, closest_lon, closest_lat) from point to segment."""
    dx = end_lon - start_lon
    dy = end_lat - start_lat
    if dx == 0.0 and dy == 0.0:
        dist = haversine_m(lon, lat, start_lon, start_lat)
        return dist, start_lon, start_lat

    t = ((lon - start_lon) * dx + (lat - start_lat) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    closest_lon = start_lon + t * dx
    closest_lat = start_lat + t * dy
    dist = haversine_m(lon, lat, closest_lon, closest_lat)
    return dist, closest_lon, closest_lat


def _segment_bearing(start_lon: float, start_lat: float, end_lon: float, end_lat: float) -> float:
    return bearing_deg(start_lon, start_lat, end_lon, end_lat)


def _edges_from_segments(segments: list[NetworkSegment]) -> list[SegmentEdge]:
    edges: list[SegmentEdge] = []
    for row in segments:
        line = to_shape(row.geometry)
        coords = list(line.coords)
        if len(coords) < 2:
            continue
        start_lon, start_lat = coords[0]
        end_lon, end_lat = coords[-1]
        length_m = row.length_m or haversine_m(start_lon, start_lat, end_lon, end_lat)
        edges.append(
            SegmentEdge(
                segment_id=row.segment_id,
                start_lon=float(start_lon),
                start_lat=float(start_lat),
                end_lon=float(end_lon),
                end_lat=float(end_lat),
                length_m=float(length_m),
                osm_way_id=row.osm_way_id,
                osm_start_node_id=row.osm_start_node_id,
                osm_end_node_id=row.osm_end_node_id,
                name=row.name,
                bearing_deg=_segment_bearing(
                    float(start_lon), float(start_lat), float(end_lon), float(end_lat)
                ),
            )
        )
    return edges


def build_segment_adjacency(edges: list[SegmentEdge]) -> dict[str, set[str]]:
    by_node: dict[int, set[str]] = {}
    for edge in edges:
        for node_id in (edge.osm_start_node_id, edge.osm_end_node_id):
            if node_id is None:
                continue
            by_node.setdefault(node_id, set()).add(edge.segment_id)

    adjacency: dict[str, set[str]] = {edge.segment_id: set() for edge in edges}
    for edge in edges:
        for node_id in (edge.osm_start_node_id, edge.osm_end_node_id):
            if node_id is None:
                continue
            for other_id in by_node.get(node_id, set()):
                if other_id != edge.segment_id:
                    adjacency[edge.segment_id].add(other_id)
    return adjacency


def gps_bearing_at(
    points: list[tuple[float, float]],
    index: int,
    *,
    min_leg_m: float = MIN_BEARING_LEG_M,
) -> tuple[float | None, bool]:
    """Return local GPS bearing (degrees) and whether it is reliable."""
    n = len(points)
    if n < 2:
        return None, False

    if 0 < index < n - 1:
        back_m = haversine_m(
            points[index - 1][0], points[index - 1][1],
            points[index][0], points[index][1],
        )
        fwd_m = haversine_m(
            points[index][0], points[index][1],
            points[index + 1][0], points[index + 1][1],
        )
        if back_m >= min_leg_m and fwd_m >= min_leg_m:
            return bearing_deg(
                points[index - 1][0], points[index - 1][1],
                points[index + 1][0], points[index + 1][1],
            ), True

    if index < n - 1:
        fwd_m = haversine_m(
            points[index][0], points[index][1],
            points[index + 1][0], points[index + 1][1],
        )
        if fwd_m >= min_leg_m:
            return bearing_deg(
                points[index][0], points[index][1],
                points[index + 1][0], points[index + 1][1],
            ), True

    if index > 0:
        back_m = haversine_m(
            points[index - 1][0], points[index - 1][1],
            points[index][0], points[index][1],
        )
        if back_m >= min_leg_m:
            return bearing_deg(
                points[index - 1][0], points[index - 1][1],
                points[index][0], points[index][1],
            ), True

    return None, False


def heading_penalty_m(angle_diff: float, *, bearing_reliable: bool) -> float | None:
    """Return extra score penalty in meters, or None to reject the candidate."""
    if not bearing_reliable:
        return 0.0
    if angle_diff <= HEADING_SOFT_DEG:
        return 0.0
    if angle_diff <= HEADING_HARD_DEG:
        span = max(HEADING_HARD_DEG - HEADING_SOFT_DEG, 1.0)
        t = (angle_diff - HEADING_SOFT_DEG) / span
        return HEADING_SOFT_PENALTY_M + t * (HEADING_HARD_PENALTY_M - HEADING_SOFT_PENALTY_M)
    return None


def continuity_penalty_m(
    prev_segment_id: str | None,
    candidate: SegmentEdge,
    *,
    edge_by_id: dict[str, SegmentEdge],
    adjacency: dict[str, set[str]],
) -> float:
    if prev_segment_id is None:
        return 0.0
    if prev_segment_id == candidate.segment_id:
        return 0.0

    prev = edge_by_id.get(prev_segment_id)
    if prev is None:
        return CONTINUITY_JUMP_M

    if candidate.segment_id in adjacency.get(prev_segment_id, set()):
        return CONTINUITY_CONNECTED_M

    if (
        prev.osm_way_id is not None
        and candidate.osm_way_id is not None
        and prev.osm_way_id == candidate.osm_way_id
    ):
        return CONTINUITY_SAME_WAY_M

    if (
        prev.name
        and candidate.name
        and prev.name == candidate.name
    ):
        return CONTINUITY_SAME_WAY_M

    turn = bearing_match_deg(prev.bearing_deg, candidate.bearing_deg)
    if 60.0 <= turn <= 120.0:
        return CONTINUITY_PERPENDICULAR_M

    return CONTINUITY_JUMP_M


def score_candidate(
    lon: float,
    lat: float,
    edge: SegmentEdge,
    *,
    gps_bearing: float | None,
    bearing_reliable: bool,
    prev_segment_id: str | None,
    edge_by_id: dict[str, SegmentEdge],
    adjacency: dict[str, set[str]],
    snap_radius_m: float,
    strict_heading: bool = True,
) -> tuple[float, float, float, float] | None:
    dist_m, clon, clat = point_to_segment_distance_m(
        lon, lat,
        edge.start_lon, edge.start_lat,
        edge.end_lon, edge.end_lat,
    )
    if dist_m > snap_radius_m:
        return None

    heading_extra = 0.0
    if gps_bearing is not None:
        angle = bearing_match_deg(gps_bearing, edge.bearing_deg)
        penalty = heading_penalty_m(angle, bearing_reliable=bearing_reliable)
        if penalty is None:
            if strict_heading:
                return None
            heading_extra = HEADING_HARD_PENALTY_M
        else:
            heading_extra = penalty

    continuity_extra = continuity_penalty_m(
        prev_segment_id,
        edge,
        edge_by_id=edge_by_id,
        adjacency=adjacency,
    )
    total = dist_m + heading_extra + continuity_extra
    return total, dist_m, clon, clat


def match_points_to_edges(
    points: list[tuple[float, float]],
    edges: list[SegmentEdge],
    *,
    snap_radius_m: float,
    edge_by_id: dict[str, SegmentEdge] | None = None,
    adjacency: dict[str, set[str]] | None = None,
) -> list[SnapHit | None]:
    if not edges:
        return [None] * len(points)

    edge_map = edge_by_id or {edge.segment_id: edge for edge in edges}
    adj = adjacency or build_segment_adjacency(edges)

    hits: list[SnapHit | None] = []
    prev_segment_id: str | None = None

    for order, (lon, lat) in enumerate(points):
        gps_bearing, bearing_reliable = gps_bearing_at(points, order)

        best: tuple[float, str, float, float, float] | None = None
        relaxed: tuple[float, str, float, float, float] | None = None
        distance_only: tuple[float, str, float, float, float] | None = None

        for edge in edges:
            scored = score_candidate(
                lon, lat, edge,
                gps_bearing=gps_bearing,
                bearing_reliable=bearing_reliable,
                prev_segment_id=prev_segment_id,
                edge_by_id=edge_map,
                adjacency=adj,
                snap_radius_m=snap_radius_m,
                strict_heading=True,
            )
            if scored is not None:
                total, dist_m, clon, clat = scored
                if best is None or total < best[0]:
                    best = (total, edge.segment_id, dist_m, clon, clat)
                continue

            relaxed_scored = score_candidate(
                lon, lat, edge,
                gps_bearing=gps_bearing,
                bearing_reliable=bearing_reliable,
                prev_segment_id=prev_segment_id,
                edge_by_id=edge_map,
                adjacency=adj,
                snap_radius_m=snap_radius_m,
                strict_heading=False,
            )
            if relaxed_scored is not None:
                total, dist_m, clon, clat = relaxed_scored
                if relaxed is None or total < relaxed[0]:
                    relaxed = (total, edge.segment_id, dist_m, clon, clat)
                continue

            if not bearing_reliable:
                dist_only, clon, clat = point_to_segment_distance_m(
                    lon, lat,
                    edge.start_lon, edge.start_lat,
                    edge.end_lon, edge.end_lat,
                )
                if dist_only <= snap_radius_m:
                    fb_score = dist_only + continuity_penalty_m(
                        prev_segment_id, edge, edge_by_id=edge_map, adjacency=adj,
                    )
                    if distance_only is None or fb_score < distance_only[0]:
                        distance_only = (fb_score, edge.segment_id, dist_only, clon, clat)

        chosen = best or relaxed or distance_only
        if chosen is None:
            hits.append(None)
            continue

        total_score, seg_id, dist_m, clon, clat = chosen
        hits.append(
            SnapHit(
                segment_id=seg_id,
                order=order,
                snap_distance_m=dist_m,
                matched_lon=clon,
                matched_lat=clat,
                total_score_m=total_score,
            )
        )
        prev_segment_id = seg_id

    return hits


def snap_points_to_edges(
    points: list[tuple[float, float]],
    edges: list[SegmentEdge],
    *,
    snap_radius_m: float,
) -> list[SnapHit | None]:
    """Backward-compatible alias for tests and simple nearest-neighbor snaps."""
    return match_points_to_edges(points, edges, snap_radius_m=snap_radius_m)


def ordered_segment_sequence(hits: list[SnapHit | None]) -> list[str]:
    sequence: list[str] = []
    prev_id: str | None = None
    for hit in hits:
        if not hit:
            continue
        if hit.segment_id != prev_id:
            sequence.append(hit.segment_id)
            prev_id = hit.segment_id
    return sequence


def reconstruct_path_coords(
    sequence: list[str],
    edge_by_id: dict[str, SegmentEdge],
) -> list[list[float]]:
    """Build a continuous LineString from ordered segment IDs."""
    if not sequence:
        return []

    coords: list[list[float]] = []
    prev_end: tuple[float, float] | None = None

    for seg_id in sequence:
        edge = edge_by_id.get(seg_id)
        if edge is None:
            continue

        start = (edge.start_lon, edge.start_lat)
        end = (edge.end_lon, edge.end_lat)

        if prev_end is not None:
            d_to_start = haversine_m(prev_end[0], prev_end[1], start[0], start[1])
            d_to_end = haversine_m(prev_end[0], prev_end[1], end[0], end[1])
            if d_to_end < d_to_start:
                start, end = end, start

        if not coords:
            coords.append([start[0], start[1]])
        elif haversine_m(coords[-1][0], coords[-1][1], start[0], start[1]) > 1.0:
            coords.append([start[0], start[1]])

        coords.append([end[0], end[1]])
        prev_end = (end[0], end[1])

    return coords


def hits_to_usage_rows(
    hits: list[SnapHit | None],
    *,
    snap_radius_m: float = DEFAULT_SNAP_M,
) -> list[UsageRow]:
    """Collapse consecutive duplicate segments; each run counts as one traversal."""
    usage: dict[str, UsageRow] = {}
    sequence_order = 0
    prev_id: str | None = None
    prev_hit: SnapHit | None = None

    for hit in hits:
        if not hit:
            prev_hit = None
            continue
        seg_id = hit.segment_id
        conf = _confidence(hit.snap_distance_m, snap_radius_m=snap_radius_m)
        if seg_id == prev_id and prev_hit is not None:
            row = usage[seg_id]
            row.matched_length_m += haversine_m(
                prev_hit.matched_lon,
                prev_hit.matched_lat,
                hit.matched_lon,
                hit.matched_lat,
            )
            row.confidence = min(row.confidence, conf)
            prev_hit = hit
            continue

        sequence_order += 1
        prev_id = seg_id
        prev_hit = hit
        if seg_id in usage:
            row = usage[seg_id]
            row.traversals += 1
            row.last_seen_order = sequence_order
            row.confidence = (row.confidence + conf) / 2.0
        else:
            usage[seg_id] = UsageRow(
                segment_id=seg_id,
                traversals=1,
                matched_length_m=0.0,
                first_seen_order=sequence_order,
                last_seen_order=sequence_order,
                confidence=conf,
            )

    return sorted(usage.values(), key=lambda r: r.first_seen_order)


def _confidence(snap_distance_m: float, *, snap_radius_m: float = DEFAULT_SNAP_M) -> float:
    if snap_radius_m <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - snap_distance_m / snap_radius_m))


def _tile_coverage(
    db: Session,
    coords: list[tuple[float, float]],
    *,
    config: TileConfig | None = None,
) -> tuple[list[str], list[str]]:
    cfg = config or get_tile_config()
    refs = tiles_for_coordinates(coords, config=cfg)
    tile_repo = CatalogTileRepository(db)
    missing: list[str] = []
    not_ready: list[str] = []
    for ref in refs:
        row = tile_repo.get(ref.tile_id)
        if not row:
            missing.append(ref.tile_id)
        elif row.status != "ready":
            not_ready.append(ref.tile_id)
    return missing, not_ready


def _set_activity_match_state(
    db: Session,
    activity_id: str,
    *,
    status: str,
    confidence: float | None,
    matched_at: datetime | None = None,
    match_diagnostics: dict | None = None,
) -> None:
    activity = db.get(Activity, activity_id)
    if activity:
        activity.match_status = status
        activity.match_confidence = confidence
        if matched_at is not None:
            activity.matched_at = matched_at
        if match_diagnostics is not None:
            activity.match_diagnostics = json.dumps(match_diagnostics)


def match_activity_catalog(
    db: Session,
    *,
    activity_id: str,
    coords: list[tuple[float, float]],
    snap_radius_m: float = DEFAULT_SNAP_M,
    sample_interval_m: float = DEFAULT_SAMPLE_M,
    allow_partial: bool = False,
    config: TileConfig | None = None,
) -> CatalogMatchResult:
    if len(coords) < 2:
        _set_activity_match_state(db, activity_id, status="failed", confidence=None)
        return CatalogMatchResult(
            activity_id=activity_id,
            status="failed",
            segment_count=0,
            points_sampled=0,
            points_matched=0,
            points_unmatched=0,
            required_tiles=0,
            ready_tiles=0,
            error="track has fewer than 2 points",
        )

    cfg = config or get_tile_config()
    missing, not_ready = _tile_coverage(db, coords, config=cfg)
    refs = tiles_for_coordinates(coords, config=cfg)
    required = len(refs)
    ready = required - len(missing) - len(not_ready)

    if missing or not_ready:
        if not allow_partial:
            parts = []
            if missing:
                parts.append(f"{len(missing)} missing")
            if not_ready:
                parts.append(f"{len(not_ready)} not ready")
            _set_activity_match_state(db, activity_id, status="failed", confidence=None)
            return CatalogMatchResult(
                activity_id=activity_id,
                status="failed",
                segment_count=0,
                points_sampled=0,
                points_matched=0,
                points_unmatched=0,
                required_tiles=required,
                ready_tiles=ready,
                missing_tiles=missing,
                not_ready_tiles=not_ready,
                error=f"catalog incomplete ({', '.join(parts)})",
            )

    bbox = compute_bbox(coords)
    search_bbox = buffer_bbox_km(bbox, max(snap_radius_m, 50.0) / 1000.0 + 0.05)
    segments = SegmentRepository(db).find_in_bbox(
        min_lon=search_bbox[0],
        min_lat=search_bbox[1],
        max_lon=search_bbox[2],
        max_lat=search_bbox[3],
    )
    if not segments:
        _set_activity_match_state(db, activity_id, status="failed", confidence=None)
        return CatalogMatchResult(
            activity_id=activity_id,
            status="failed",
            segment_count=0,
            points_sampled=0,
            points_matched=0,
            points_unmatched=0,
            required_tiles=required,
            ready_tiles=ready,
            missing_tiles=missing,
            not_ready_tiles=not_ready,
            error="no catalog segments in activity bbox",
        )

    edges = _edges_from_segments(segments)
    edge_by_id = {edge.segment_id: edge for edge in edges}
    adjacency = build_segment_adjacency(edges)

    sampled = sample_track(coords, interval_m=sample_interval_m)
    hits = match_points_to_edges(
        sampled,
        edges,
        snap_radius_m=snap_radius_m,
        edge_by_id=edge_by_id,
        adjacency=adjacency,
    )
    from app.core.catalog_match_cleanup import cleanup_matched_hits

    hits, cleanup_stats = cleanup_matched_hits(hits, sampled, edge_by_id)
    segment_sequence = ordered_segment_sequence(hits)
    matched_coords = reconstruct_path_coords(segment_sequence, edge_by_id)
    usage_rows = hits_to_usage_rows(hits, snap_radius_m=snap_radius_m)

    matched_n = sum(1 for h in hits if h)
    unmatched_n = len(hits) - matched_n
    confidences = [h.snap_distance_m for h in hits if h]
    avg_snap = sum(confidences) / len(confidences) if confidences else None
    match_confidence = (
        _confidence(avg_snap, snap_radius_m=snap_radius_m) if avg_snap is not None else None
    )

    if not usage_rows:
        _set_activity_match_state(
            db, activity_id, status="failed", confidence=match_confidence
        )
        return CatalogMatchResult(
            activity_id=activity_id,
            status="failed",
            segment_count=0,
            points_sampled=len(sampled),
            points_matched=matched_n,
            points_unmatched=unmatched_n,
            required_tiles=required,
            ready_tiles=ready,
            missing_tiles=missing,
            not_ready_tiles=not_ready,
            match_confidence=match_confidence,
            error="no segments matched within snap radius",
        )

    SegmentUsageRepository(db).replace_for_activity(
        activity_id,
        [
            UsageDraft(
                segment_id=row.segment_id,
                traversals=row.traversals,
                matched_length_m=row.matched_length_m,
                first_seen_order=row.first_seen_order,
                last_seen_order=row.last_seen_order,
                confidence=row.confidence,
            )
            for row in usage_rows
        ],
    )

    partial = bool(missing or not_ready)
    status = "partial" if partial else "matched"
    matched_distance_m = sum(row.matched_length_m for row in usage_rows)
    diagnostics = {
        "segment_sequence_length": len(segment_sequence),
        "unique_segments": len(usage_rows),
        "matched_distance_m": matched_distance_m,
        "low_support_segment_count": cleanup_stats.low_support_segment_count,
        "suppressed_spur_count": cleanup_stats.suppressed_spur_count,
        "weak_turn_reassignments": cleanup_stats.weak_turn_reassignments,
        "points_sampled": len(sampled),
        "points_matched": matched_n,
        "points_unmatched": unmatched_n,
    }
    _set_activity_match_state(
        db,
        activity_id,
        status=status,
        confidence=match_confidence,
        matched_at=datetime.utcnow(),
        match_diagnostics=diagnostics,
    )

    return CatalogMatchResult(
        activity_id=activity_id,
        status=status,
        segment_count=len(usage_rows),
        points_sampled=len(sampled),
        points_matched=matched_n,
        points_unmatched=unmatched_n,
        required_tiles=required,
        ready_tiles=ready,
        missing_tiles=missing,
        not_ready_tiles=not_ready,
        match_confidence=match_confidence,
        usage=usage_rows,
        segment_sequence=segment_sequence,
        matched_coords=matched_coords,
    )


def sample_track(
    coords: list[tuple[float, float]],
    *,
    interval_m: float,
) -> list[tuple[float, float]]:
    if not coords:
        return []
    if len(coords) == 1 or interval_m <= 0:
        return list(coords)

    out = [coords[0]]
    carry = 0.0
    for idx in range(1, len(coords)):
        lon1, lat1 = coords[idx - 1]
        lon2, lat2 = coords[idx]
        seg_len = haversine_m(lon1, lat1, lon2, lat2)
        if seg_len <= 0:
            continue

        dist_along = interval_m - carry
        while dist_along <= seg_len:
            t = dist_along / seg_len
            out.append((lon1 + t * (lon2 - lon1), lat1 + t * (lat2 - lat1)))
            dist_along += interval_m
        carry = max(0.0, seg_len - (dist_along - interval_m))

    if out[-1] != coords[-1]:
        out.append(coords[-1])
    return out


def match_activity_from_geojson(
    db: Session,
    *,
    activity_id: str,
    geojson_path: Path,
    **kwargs,
) -> CatalogMatchResult:
    coords = coords_from_geojson(geojson_path)
    return match_activity_catalog(db, activity_id=activity_id, coords=coords, **kwargs)


def write_matched_geojson(
    path: Path,
    *,
    activity_id: str,
    matched_coords: list[list[float]],
) -> None:
    if len(matched_coords) < 2:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": activity_id,
                    "variant": "matched",
                    "matcher": "catalog",
                    "geometry_source": "segment_path",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": matched_coords,
                },
            }
        ],
    }
    path.write_text(json.dumps(fc), encoding="utf-8")
