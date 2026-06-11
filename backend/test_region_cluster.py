from __future__ import annotations

from pathlib import Path

from app.core.geo import haversine_m
from app.core.parse_gpx import ParsedTrack
from app.core.region_cluster import ActivityDraft, cluster_drafts, draft_from_track
from datetime import datetime, timezone


def _track_at(lat: float, lon: float) -> ParsedTrack:
    t0 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    return ParsedTrack(
        name="test",
        activity_type="run",
        start_time_utc=t0,
        end_time_utc=t0,
        duration_sec=3600,
        distance_m=5000,
        elev_gain_m=None,
        coordinates=[(lon, lat), (lon + 0.01, lat + 0.01)],
    )


def test_cluster_distant_activities_form_separate_regions():
    pa = draft_from_track(
        activity_id="a1",
        file_path=Path("a.gpx"),
        source_format="GPX",
        track=_track_at(40.0, -75.0),
        hash_sig="h1",
    )
    fl = draft_from_track(
        activity_id="a2",
        file_path=Path("b.gpx"),
        source_format="GPX",
        track=_track_at(28.4, -81.5),
        hash_sig="h2",
    )
    clusters = cluster_drafts([pa, fl], threshold_km=10.0)
    assert len(clusters) == 2


def test_cluster_nearby_activities_form_one_region():
    a = draft_from_track(
        activity_id="a1",
        file_path=Path("a.gpx"),
        source_format="GPX",
        track=_track_at(40.0, -75.0),
        hash_sig="h1",
    )
    b = draft_from_track(
        activity_id="a2",
        file_path=Path("b.gpx"),
        source_format="GPX",
        track=_track_at(40.05, -75.05),
        hash_sig="h2",
    )
    clusters = cluster_drafts([a, b], threshold_km=10.0)
    assert len(clusters) == 1
    assert len(clusters[0].members) == 2


def test_cluster_threshold_boundary():
    """Activities ~15 km apart should split at 10 km threshold."""
    a = draft_from_track(
        activity_id="a1",
        file_path=Path("a.gpx"),
        source_format="GPX",
        track=_track_at(40.0, -75.0),
        hash_sig="h1",
    )
    # ~0.12 deg lat ≈ 13 km north
    b = draft_from_track(
        activity_id="a2",
        file_path=Path("b.gpx"),
        source_format="GPX",
        track=_track_at(40.12, -75.0),
        hash_sig="h2",
    )
    dist = haversine_m(-75.0, 40.0, -75.0, 40.12)
    assert dist > 10_000
    clusters = cluster_drafts([a, b], threshold_km=10.0)
    assert len(clusters) == 2
