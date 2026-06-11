from __future__ import annotations

from datetime import datetime, timezone

from app.core.catalog_tiles import (
    TileConfig,
    buffer_bbox_km,
    get_tile_config,
    tile_bbox_for_indices,
    tile_ref_for_indices,
    tiles_for_bbox,
    tiles_for_coordinates,
)
from app.core.parse_gpx import ParsedTrack
from app.db.segment_ids import make_tile_id, make_tile_scheme


def _track_line(lons_lats: list[tuple[float, float]]) -> ParsedTrack:
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    return ParsedTrack(
        name="test",
        activity_type="run",
        start_time_utc=t0,
        end_time_utc=t0,
        duration_sec=3600,
        distance_m=5000,
        elev_gain_m=None,
        coordinates=[(lon, lat) for lon, lat in lons_lats],
    )


def test_make_tile_scheme_encodes_size():
    assert make_tile_scheme(5.0) == "latlon-5000m-v1"
    assert make_tile_scheme(2.5) == "latlon-2500m-v1"


def test_make_tile_id_is_stable():
    scheme = make_tile_scheme(5.0)
    assert make_tile_id(scheme, 482, -1247) == "tile_latlon-5000m-v1_482_-1247"


def test_tile_bbox_and_fetch_margin():
    cfg = TileConfig(
        tile_km=5.0,
        activity_buffer_km=0.5,
        fetch_margin_m=350.0,
        catalog_version="1",
        tile_scheme_version="v1",
    )
    ref = tile_ref_for_indices(100, 200, config=cfg)
    core = ref.bbox
    fetch = ref.fetch_bbox
    assert fetch[0] < core[0]
    assert fetch[1] < core[1]
    assert fetch[2] > core[2]
    assert fetch[3] > core[3]


def test_different_tile_km_produces_different_tile_ids():
    cfg5 = TileConfig(5.0, 0.5, 350.0, "1", "v1")
    cfg25 = TileConfig(2.5, 0.5, 350.0, "1", "v1")
    ref5 = tile_ref_for_indices(482, -1247, config=cfg5)
    ref25 = tile_ref_for_indices(482, -1247, config=cfg25)
    assert ref5.tile_id != ref25.tile_id
    assert ref5.tile_scheme != ref25.tile_scheme


def test_tiles_for_coordinates_uses_buffered_bbox():
    track = _track_line([(-75.52, 40.59), (-75.50, 40.60)])
    cfg = TileConfig(5.0, 0.5, 350.0, "1", "v1")
    tiles = tiles_for_coordinates(track.coordinates, config=cfg)
    assert len(tiles) >= 1
    for ref in tiles:
        assert ref.tile_scheme == cfg.tile_scheme
        assert ref.catalog_version == "1"


def test_smaller_activity_buffer_fewer_tiles_than_large_buffer():
    coords = [(-75.52, 40.59), (-75.40, 40.70)]
    small = TileConfig(5.0, 0.5, 350.0, "1", "v1")
    large = TileConfig(5.0, 2.0, 350.0, "1", "v1")
    assert len(tiles_for_coordinates(coords, config=small)) <= len(
        tiles_for_coordinates(coords, config=large)
    )


def test_tiles_for_bbox_returns_at_least_one_tile():
    cfg = TileConfig(5.0, 0.5, 350.0, "1", "v1")
    bbox = (-75.55, 40.55, -75.45, 40.65)
    tiles = tiles_for_bbox(bbox, config=cfg)
    assert len(tiles) >= 1
    assert all(t.tile_scheme == cfg.tile_scheme for t in tiles)


def test_tile_indices_round_trip_bbox_contains_sw_corner():
    cfg = get_tile_config()
    ref = tile_ref_for_indices(482, -1247, config=cfg)
    min_lon, min_lat, max_lon, max_lat = ref.bbox
    assert min_lon < max_lon
    assert min_lat < max_lat
    again = tile_bbox_for_indices(ref.lat_idx, ref.lon_idx, cfg.tile_km)
    assert again == ref.bbox


def test_buffer_bbox_km_expands():
    bbox = (-75.0, 40.0, -74.9, 40.1)
    out = buffer_bbox_km(bbox, 0.5)
    assert out[0] < bbox[0]
    assert out[2] > bbox[2]
