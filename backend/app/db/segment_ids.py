from __future__ import annotations

import hashlib


def make_segment_id(
    osm_way_id: int | str,
    osm_start_node_id: int | str,
    osm_end_node_id: int | str,
) -> str:
    """Stable business identity for a network edge.

    Uses OSM way + node pair with canonical (undirected) ordering so the same
    physical segment always receives the same ID regardless of traversal direction.
    """
    way = int(osm_way_id)
    a, b = sorted((int(osm_start_node_id), int(osm_end_node_id)))
    return f"osm:{way}:{a}:{b}"


def make_region_id(
    centroid_lat: float,
    centroid_lon: float,
    *,
    precision: int = 2,
) -> str:
    """Derive a stable global region identifier from a cluster centroid."""
    lat = round(centroid_lat, precision)
    lon = round(centroid_lon, precision)
    digest = hashlib.sha1(f"{lat},{lon}".encode("utf-8")).hexdigest()[:12]
    return f"reg_{digest}"


def make_region_name(
    centroid_lat: float,
    centroid_lon: float,
    *,
    precision: int = 2,
) -> str:
    """Human-readable display name from rounded centroid coordinates."""
    lat_r = round(centroid_lat, precision)
    lon_r = round(centroid_lon, precision)
    lat_suffix = "N" if lat_r >= 0 else "S"
    lon_suffix = "E" if lon_r >= 0 else "W"
    return (
        f"{abs(lat_r):.{precision}f}°{lat_suffix}, "
        f"{abs(lon_r):.{precision}f}°{lon_suffix}"
    )


def make_activity_id(customer_id: str, hash_sig: str) -> str:
    """Stable activity key scoped to one customer."""
    digest = hashlib.sha1(f"{customer_id}|{hash_sig}".encode("utf-8")).hexdigest()[:32]
    return f"act_{digest}"


def make_tile_scheme(tile_km: float, *, version: str = "v1") -> str:
    """Identify grid rules — encodes tile size so 5 km and 2.5 km cells stay distinct."""
    size_m = int(round(tile_km * 1000))
    return f"latlon-{size_m}m-{version}"


def make_tile_id(tile_scheme: str, lat_idx: int, lon_idx: int) -> str:
    """Stable global tile key for one scheme + grid indices."""
    safe_scheme = tile_scheme.replace(".", "p")
    return f"tile_{safe_scheme}_{lat_idx}_{lon_idx}"
