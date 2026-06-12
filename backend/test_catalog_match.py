from app.core.catalog_match import (
    SegmentEdge,
    SnapHit,
    build_segment_adjacency,
    continuity_penalty_m,
    gps_bearing_at,
    heading_penalty_m,
    hits_to_usage_rows,
    match_points_to_edges,
    ordered_segment_sequence,
    point_to_segment_distance_m,
    reconstruct_path_coords,
    sample_track,
    snap_points_to_edges,
)
from app.core.catalog_match_cleanup import (
    build_segment_runs,
    cleanup_matched_hits,
    is_spur_run,
)
from app.core.geo import bearing_match_deg


def test_point_on_segment_midpoint():
    dist, lon, lat = point_to_segment_distance_m(
        -75.5, 40.6,
        -75.51, 40.59,
        -75.49, 40.61,
    )
    assert dist < 1.0
    assert abs(lon - (-75.5)) < 0.0001
    assert abs(lat - 40.6) < 0.0001


def test_sample_track_adds_intermediate_points():
    coords = [(-75.5, 40.6), (-75.49, 40.61)]
    sampled = sample_track(coords, interval_m=200.0)
    assert len(sampled) >= 2
    assert sampled[0] == coords[0]
    assert sampled[-1] == coords[-1]


def test_hits_to_usage_merges_consecutive_segments():
    hits = [
        SnapHit("osm:1:2:3", 0, 5.0, -75.5, 40.6),
        SnapHit("osm:1:2:3", 1, 4.0, -75.499, 40.601),
        SnapHit("osm:4:5:6", 2, 6.0, -75.498, 40.602),
        SnapHit("osm:1:2:3", 3, 7.0, -75.497, 40.603),
    ]
    rows = hits_to_usage_rows(hits, snap_radius_m=40.0)
    assert len(rows) == 2
    by_id = {r.segment_id: r for r in rows}
    assert by_id["osm:1:2:3"].traversals == 2
    assert by_id["osm:4:5:6"].traversals == 1
    assert by_id["osm:1:2:3"].matched_length_m > 0


def test_snap_points_to_nearest_edge():
    edges = [
        SegmentEdge("seg_a", -75.51, 40.59, -75.49, 40.61, 2500.0),
    ]
    hits = snap_points_to_edges(
        [(-75.5, 40.6)],
        edges,
        snap_radius_m=50.0,
    )
    assert hits[0] is not None
    assert hits[0].segment_id == "seg_a"
    assert hits[0].snap_distance_m < 50.0


def test_heading_prefers_parallel_road_at_intersection():
    # Main road runs north-south; GPS is ~3 m east (typical offset) traveling north.
    road_lon = -75.498000
    gps_lon = -75.497970
    main = SegmentEdge(
        "main_ns",
        road_lon, 40.590,
        road_lon, 40.610,
        2200.0,
        osm_way_id=1,
        osm_start_node_id=10,
        osm_end_node_id=11,
        name="North Ott Street",
        bearing_deg=0.0,
    )
    cross = SegmentEdge(
        "cross_ew",
        -75.510, 40.600,
        -75.490, 40.600,
        1700.0,
        osm_way_id=2,
        osm_start_node_id=20,
        osm_end_node_id=21,
        name="James Street",
        bearing_deg=90.0,
    )
    edges = [main, cross]
    edge_by_id = {e.segment_id: e for e in edges}
    adjacency = build_segment_adjacency(edges)

    points = [
        (gps_lon, 40.595),
        (gps_lon, 40.600),
        (gps_lon, 40.605),
    ]
    bearing, reliable = gps_bearing_at(points, 1)
    assert reliable
    assert bearing is not None
    assert bearing_match_deg(bearing, main.bearing_deg) < 30.0

    hits = match_points_to_edges(
        points,
        edges,
        snap_radius_m=50.0,
        edge_by_id=edge_by_id,
        adjacency=adjacency,
    )
    assert all(h is not None for h in hits)
    assert all(h.segment_id == "main_ns" for h in hits)


def test_continuity_penalizes_perpendicular_jump():
    prev = SegmentEdge(
        "main_ns", -75.5, 40.59, -75.5, 40.61, 2000.0,
        osm_way_id=1, osm_start_node_id=1, osm_end_node_id=2,
        bearing_deg=0.0,
    )
    side = SegmentEdge(
        "side_ew", -75.51, 40.60, -75.49, 40.60, 1500.0,
        osm_way_id=2, osm_start_node_id=3, osm_end_node_id=4,
        bearing_deg=90.0,
    )
    edge_by_id = {prev.segment_id: prev, side.segment_id: side}
    adjacency = build_segment_adjacency([prev, side])

    same_penalty = continuity_penalty_m(
        "main_ns", prev, edge_by_id=edge_by_id, adjacency=adjacency,
    )
    cross_penalty = continuity_penalty_m(
        "main_ns", side, edge_by_id=edge_by_id, adjacency=adjacency,
    )
    assert same_penalty == 0.0
    assert cross_penalty > same_penalty


def test_heading_penalty_rejects_large_mismatch_when_reliable():
    assert heading_penalty_m(30.0, bearing_reliable=True) == 0.0
    assert heading_penalty_m(50.0, bearing_reliable=True) is not None
    assert heading_penalty_m(75.0, bearing_reliable=True) is None
    assert heading_penalty_m(75.0, bearing_reliable=False) == 0.0


def test_build_segment_runs_tracks_support():
    road_lon = -75.498000
    gps_lon = -75.497970
    main = SegmentEdge(
        "main_ns", road_lon, 40.590, road_lon, 40.610, 2200.0,
        osm_way_id=1, osm_start_node_id=10, osm_end_node_id=11,
        name="Main", bearing_deg=0.0,
    )
    spur = SegmentEdge(
        "spur_ew", road_lon, 40.600, -75.497900, 40.600, 30.0,
        osm_way_id=2, osm_start_node_id=20, osm_end_node_id=21,
        name="Service", bearing_deg=90.0,
    )
    edge_by_id = {main.segment_id: main, spur.segment_id: spur}
    points = [
        (gps_lon, 40.595),
        (gps_lon, 40.600),
        (gps_lon, 40.605),
    ]
    hits = [
        SnapHit("main_ns", 0, 3.0, road_lon, 40.595),
        SnapHit("spur_ew", 1, 2.0, road_lon, 40.600),
        SnapHit("main_ns", 2, 3.0, road_lon, 40.605),
    ]
    runs = build_segment_runs(hits, points, edge_by_id)
    assert len(runs) == 3
    assert runs[1].gps_point_count == 1
    assert runs[1].segment_id == "spur_ew"
    assert is_spur_run(runs, 1, edge_by_id)


def test_cleanup_enforces_sustained_turn():
    road_lon = -75.498000
    main = SegmentEdge(
        "main_ns", road_lon, 40.590, road_lon, 40.610, 2200.0,
        osm_way_id=1, osm_start_node_id=10, osm_end_node_id=11,
        name="Main", bearing_deg=0.0,
    )
    side = SegmentEdge(
        "side_ew", road_lon, 40.600, -75.497800, 40.600, 120.0,
        osm_way_id=3, osm_start_node_id=30, osm_end_node_id=31,
        name="Side", bearing_deg=90.0,
    )
    edge_by_id = {main.segment_id: main, side.segment_id: side}
    points = [
        (road_lon, 40.595),
        (road_lon, 40.598),
        (road_lon, 40.600),
        (road_lon, 40.603),
        (road_lon, 40.606),
    ]
    hits = [
        SnapHit("main_ns", 0, 2.0, road_lon, 40.595),
        SnapHit("main_ns", 1, 2.0, road_lon, 40.598),
        SnapHit("side_ew", 2, 2.0, road_lon, 40.600),
        SnapHit("main_ns", 3, 2.0, road_lon, 40.603),
        SnapHit("main_ns", 4, 2.0, road_lon, 40.606),
    ]
    cleaned, stats = cleanup_matched_hits(hits, points, edge_by_id)
    assert cleaned[2] is not None
    assert cleaned[2].segment_id == "main_ns"
    assert stats.suppressed_spur_count >= 0
    usage = hits_to_usage_rows(cleaned, snap_radius_m=40.0)
    assert len(usage) == 1
    assert usage[0].segment_id == "main_ns"


def test_cleanup_removes_short_spur():
    road_lon = -75.498000
    gps_lon = -75.497970
    main = SegmentEdge(
        "main_ns", road_lon, 40.590, road_lon, 40.610, 2200.0,
        osm_way_id=1, osm_start_node_id=10, osm_end_node_id=11,
        name="Main", bearing_deg=0.0,
    )
    spur = SegmentEdge(
        "spur_ew", road_lon, 40.600, -75.497900, 40.600, 30.0,
        osm_way_id=2, osm_start_node_id=20, osm_end_node_id=21,
        name="Service", bearing_deg=90.0,
    )
    edge_by_id = {main.segment_id: main, spur.segment_id: spur}
    points = [
        (gps_lon, 40.595),
        (gps_lon, 40.600),
        (gps_lon, 40.605),
    ]
    hits = [
        SnapHit("main_ns", 0, 3.0, road_lon, 40.595),
        SnapHit("spur_ew", 1, 2.0, road_lon, 40.600),
        SnapHit("main_ns", 2, 3.0, road_lon, 40.605),
    ]
    cleaned, stats = cleanup_matched_hits(hits, points, edge_by_id)
    assert cleaned[1] is not None
    assert cleaned[1].segment_id == "main_ns"
    assert stats.suppressed_spur_count >= 1 or stats.weak_turn_reassignments >= 1
    seq = ordered_segment_sequence(cleaned)
    assert seq == ["main_ns"]


def test_ordered_segment_sequence_and_reconstruct():
    hits = [
        SnapHit("a", 0, 1.0, -75.5, 40.6),
        SnapHit("a", 1, 1.0, -75.499, 40.601),
        SnapHit("b", 2, 1.0, -75.498, 40.602),
    ]
    seq = ordered_segment_sequence(hits)
    assert seq == ["a", "b"]

    edge_by_id = {
        "a": SegmentEdge("a", -75.5, 40.6, -75.499, 40.601, 120.0,
                         osm_start_node_id=1, osm_end_node_id=2),
        "b": SegmentEdge("b", -75.499, 40.601, -75.498, 40.602, 120.0,
                         osm_start_node_id=2, osm_end_node_id=3),
    }
    coords = reconstruct_path_coords(seq, edge_by_id)
    assert len(coords) >= 3
    assert coords[0] == [-75.5, 40.6]
    assert coords[-1] == [-75.498, 40.602]
