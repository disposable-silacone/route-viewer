from __future__ import annotations

import math
import os
from dataclasses import dataclass

from app.core.geo import compute_bbox
from app.db.segment_ids import make_tile_id, make_tile_scheme

M_PER_DEG_LAT = 111_320.0

DEFAULT_TILE_KM = float(os.getenv("CATALOG_TILE_KM", "5"))
DEFAULT_ACTIVITY_BUFFER_KM = float(os.getenv("CATALOG_ACTIVITY_BUFFER_KM", "0.5"))
DEFAULT_FETCH_MARGIN_M = float(os.getenv("CATALOG_FETCH_MARGIN_M", "350"))
DEFAULT_CATALOG_VERSION = os.getenv("CATALOG_VERSION", "1")
DEFAULT_TILE_SCHEME_VERSION = os.getenv("CATALOG_TILE_SCHEME_VERSION", "v1")


@dataclass(frozen=True)
class TileConfig:
    tile_km: float
    activity_buffer_km: float
    fetch_margin_m: float
    catalog_version: str
    tile_scheme_version: str

    @property
    def tile_scheme(self) -> str:
        return make_tile_scheme(self.tile_km, version=self.tile_scheme_version)


@dataclass(frozen=True)
class TileRef:
    """One catalog tile cell — core bbox plus OSM fetch extent (includes build margin)."""

    tile_id: str
    tile_scheme: str
    catalog_version: str
    lat_idx: int
    lon_idx: int
    bbox: tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat
    fetch_bbox: tuple[float, float, float, float]


def get_tile_config() -> TileConfig:
    return TileConfig(
        tile_km=DEFAULT_TILE_KM,
        activity_buffer_km=DEFAULT_ACTIVITY_BUFFER_KM,
        fetch_margin_m=DEFAULT_FETCH_MARGIN_M,
        catalog_version=DEFAULT_CATALOG_VERSION,
        tile_scheme_version=DEFAULT_TILE_SCHEME_VERSION,
    )


def lat_idx_for(lat: float, tile_km: float) -> int:
    return int(math.floor((lat + 90.0) * M_PER_DEG_LAT / (tile_km * 1000.0)))


def lat_band_center(lat_idx: int, tile_km: float) -> float:
    tile_deg = tile_km * 1000.0 / M_PER_DEG_LAT
    sw = lat_idx * tile_deg - 90.0
    return sw + tile_deg / 2.0


def lon_idx_for(lon: float, lat_band_center_deg: float, tile_km: float) -> int:
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat_band_center_deg))
    if m_per_deg_lon <= 0:
        m_per_deg_lon = 1e-6
    return int(math.floor((lon + 180.0) * m_per_deg_lon / (tile_km * 1000.0)))


def tile_bbox_for_indices(
    lat_idx: int,
    lon_idx: int,
    tile_km: float,
) -> tuple[float, float, float, float]:
    tile_deg_lat = tile_km * 1000.0 / M_PER_DEG_LAT
    lat_sw = lat_idx * tile_deg_lat - 90.0
    lat_ne = lat_sw + tile_deg_lat
    center = (lat_sw + lat_ne) / 2.0
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(center))
    if m_per_deg_lon <= 0:
        m_per_deg_lon = 1e-6
    tile_deg_lon = tile_km * 1000.0 / m_per_deg_lon
    lon_sw = lon_idx * tile_deg_lon - 180.0
    lon_ne = lon_sw + tile_deg_lon
    return (lon_sw, lat_sw, lon_ne, lat_ne)


def expand_bbox_m(
    bbox: tuple[float, float, float, float],
    margin_m: float,
    ref_lat: float | None = None,
) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = ref_lat if ref_lat is not None else (min_lat + max_lat) / 2.0
    lat_margin = margin_m / M_PER_DEG_LAT
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(center_lat))
    if m_per_deg_lon <= 0:
        m_per_deg_lon = 1e-6
    lon_margin = margin_m / m_per_deg_lon
    return (
        min_lon - lon_margin,
        min_lat - lat_margin,
        max_lon + lon_margin,
        max_lat + lat_margin,
    )


def buffer_bbox_km(
    bbox: tuple[float, float, float, float],
    buffer_km: float,
) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    ref_lat = (min_lat + max_lat) / 2.0
    lat_margin = buffer_km * 1000.0 / M_PER_DEG_LAT
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ref_lat))
    if m_per_deg_lon <= 0:
        m_per_deg_lon = 1e-6
    lon_margin = buffer_km * 1000.0 / m_per_deg_lon
    return (
        min_lon - lon_margin,
        min_lat - lat_margin,
        max_lon + lon_margin,
        max_lat + lat_margin,
    )


def tile_ref_for_indices(
    lat_idx: int,
    lon_idx: int,
    *,
    config: TileConfig | None = None,
) -> TileRef:
    cfg = config or get_tile_config()
    bbox = tile_bbox_for_indices(lat_idx, lon_idx, cfg.tile_km)
    center = lat_band_center(lat_idx, cfg.tile_km)
    fetch_bbox = expand_bbox_m(bbox, cfg.fetch_margin_m, ref_lat=center)
    tile_scheme = cfg.tile_scheme
    return TileRef(
        tile_id=make_tile_id(tile_scheme, lat_idx, lon_idx),
        tile_scheme=tile_scheme,
        catalog_version=cfg.catalog_version,
        lat_idx=lat_idx,
        lon_idx=lon_idx,
        bbox=bbox,
        fetch_bbox=fetch_bbox,
    )


def tiles_for_bbox(
    bbox: tuple[float, float, float, float],
    *,
    config: TileConfig | None = None,
) -> list[TileRef]:
    cfg = config or get_tile_config()
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_min = lat_idx_for(min_lat, cfg.tile_km)
    lat_max = lat_idx_for(max_lat, cfg.tile_km)

    seen: dict[str, TileRef] = {}
    for lat_idx in range(lat_min, lat_max + 1):
        center = lat_band_center(lat_idx, cfg.tile_km)
        lon_min = lon_idx_for(min_lon, center, cfg.tile_km)
        lon_max = lon_idx_for(max_lon, center, cfg.tile_km)
        for lon_idx in range(lon_min, lon_max + 1):
            ref = tile_ref_for_indices(lat_idx, lon_idx, config=cfg)
            seen[ref.tile_id] = ref
    return list(seen.values())


def tiles_for_coordinates(
    coordinates: list[tuple[float, float]],
    *,
    config: TileConfig | None = None,
) -> list[TileRef]:
    """Return catalog tiles touched by activity geometry.

    v1: buffer the route bbox. Future: corridor buffer along the linestring
    (e.g. activity_buffer_km perpendicular to the polyline) for tighter tiling.
    """
    if not coordinates:
        return []
    cfg = config or get_tile_config()
    bbox = compute_bbox(coordinates)
    buffered = buffer_bbox_km(bbox, cfg.activity_buffer_km)
    return tiles_for_bbox(buffered, config=cfg)


def tiles_for_stored_bbox(
    bbox: tuple[float, float, float, float],
    *,
    config: TileConfig | None = None,
) -> list[TileRef]:
    """Coverage fallback when only a stored activity bbox is available."""
    cfg = config or get_tile_config()
    buffered = buffer_bbox_km(bbox, cfg.activity_buffer_km)
    return tiles_for_bbox(buffered, config=cfg)


def parse_bbox_string(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        return None
    try:
        vals = tuple(float(p) for p in parts)
    except ValueError:
        return None
    return vals  # min_lon, min_lat, max_lon, max_lat
