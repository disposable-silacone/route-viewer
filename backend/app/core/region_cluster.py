from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.geo import (
    buffer_bbox,
    compute_bbox,
    compute_centroid,
    haversine_m,
    union_bbox,
)
from app.core.parse_gpx import ParsedTrack
from app.db.segment_ids import make_region_id


@dataclass
class ActivityDraft:
    """Parsed activity ready for clustering and persistence."""

    activity_id: str
    file_path: Path
    source_format: str
    track: ParsedTrack
    hash_sig: str
    centroid_lat: float
    centroid_lon: float
    bbox: tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat


@dataclass
class ActivityCluster:
    """Group of activities that share a geographic processing region."""

    members: list[ActivityDraft] = field(default_factory=list)

    @property
    def centroid_lat(self) -> float:
        return sum(m.centroid_lat for m in self.members) / len(self.members)

    @property
    def centroid_lon(self) -> float:
        return sum(m.centroid_lon for m in self.members) / len(self.members)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return union_bbox([m.bbox for m in self.members])

    def distance_to_m(self, lat: float, lon: float) -> float:
        return haversine_m(self.centroid_lon, self.centroid_lat, lon, lat)


def draft_from_track(
    *,
    activity_id: str,
    file_path: Path,
    source_format: str,
    track: ParsedTrack,
    hash_sig: str,
) -> ActivityDraft:
    lat, lon = compute_centroid(track.coordinates)
    return ActivityDraft(
        activity_id=activity_id,
        file_path=file_path,
        source_format=source_format,
        track=track,
        hash_sig=hash_sig,
        centroid_lat=lat,
        centroid_lon=lon,
        bbox=compute_bbox(track.coordinates),
    )


def _draft_sort_key(draft: ActivityDraft) -> tuple:
    started = draft.track.start_time_utc
    if started is None:
        return (1, datetime.min.replace(tzinfo=timezone.utc), draft.hash_sig)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (0, started, draft.hash_sig)


def cluster_drafts(
    drafts: list[ActivityDraft],
    *,
    threshold_km: float = 10.0,
) -> list[ActivityCluster]:
    """Greedy centroid clustering — assign each activity to the nearest cluster within threshold."""
    threshold_m = threshold_km * 1000.0
    clusters: list[ActivityCluster] = []

    for draft in sorted(drafts, key=_draft_sort_key):
        best: ActivityCluster | None = None
        best_dist = float("inf")

        for cluster in clusters:
            dist = cluster.distance_to_m(draft.centroid_lat, draft.centroid_lon)
            if dist <= threshold_m and dist < best_dist:
                best = cluster
                best_dist = dist

        if best is not None:
            best.members.append(draft)
        else:
            clusters.append(ActivityCluster(members=[draft]))

    return clusters


def merge_clusters_by_region_id(clusters: list[ActivityCluster]) -> list[ActivityCluster]:
    """Merge clusters that share the same global region_id (2dp centroid grid)."""
    merged: dict[str, ActivityCluster] = {}
    order: list[str] = []

    for cluster in clusters:
        region_id = make_region_id(cluster.centroid_lat, cluster.centroid_lon)
        if region_id in merged:
            merged[region_id].members.extend(cluster.members)
        else:
            merged[region_id] = ActivityCluster(members=list(cluster.members))
            order.append(region_id)

    return [merged[rid] for rid in order]


def region_bbox_for_cluster(
    cluster: ActivityCluster,
    *,
    buffer_deg: float = 0.02,
) -> tuple[float, float, float, float]:
    """Cluster union bbox with a small buffer (~2 km at mid-latitudes)."""
    return buffer_bbox(cluster.bbox, buffer_deg)
