from __future__ import annotations

import math


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters between two lon/lat points."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def compute_bbox(coords: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat)."""
    if not coords:
        return (0.0, 0.0, 0.0, 0.0)
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (min(lons), min(lats), max(lons), max(lats))


def compute_centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Return (lat, lon) centroid of coordinates."""
    if not coords:
        return (0.0, 0.0)
    lon_sum = sum(c[0] for c in coords)
    lat_sum = sum(c[1] for c in coords)
    n = len(coords)
    return (lat_sum / n, lon_sum / n)


def union_bbox(
    boxes: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Union of (min_lon, min_lat, max_lon, max_lat) boxes."""
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def buffer_bbox(
    bbox: tuple[float, float, float, float],
    buffer_deg: float,
) -> tuple[float, float, float, float]:
    """Expand a bbox by buffer_deg on each side (approximate degrees)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        min_lon - buffer_deg,
        min_lat - buffer_deg,
        max_lon + buffer_deg,
        max_lat + buffer_deg,
    )


def bbox_to_string(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(str(v) for v in bbox)


def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Initial bearing in degrees [0, 360) from point 1 to point 2."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest difference between two bearings in degrees [0, 180]."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def bearing_match_deg(gps_bearing: float, segment_bearing: float) -> float:
    """Min angle between GPS heading and segment direction (either travel sense)."""
    fwd = angle_diff_deg(gps_bearing, segment_bearing)
    rev = angle_diff_deg(gps_bearing, (segment_bearing + 180.0) % 360.0)
    return min(fwd, rev)
