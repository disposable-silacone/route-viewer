from __future__ import annotations

import json
from pathlib import Path


def coords_from_geojson(path: Path) -> list[tuple[float, float]]:
    """Return (lon, lat) points from the main LineString in a GeoJSON file."""
    fc = json.loads(path.read_text(encoding="utf-8"))
    features = fc.get("features") or []
    for feature in features:
        geom = feature.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        raw = geom.get("coordinates") or []
        return [(float(c[0]), float(c[1])) for c in raw]
    return []


def coords_from_geojson_dict(data: dict) -> list[tuple[float, float]]:
    features = data.get("features") or []
    for feature in features:
        geom = feature.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        raw = geom.get("coordinates") or []
        return [(float(c[0]), float(c[1])) for c in raw]
    geom = data.get("geometry")
    if geom and geom.get("type") == "LineString":
        raw = geom.get("coordinates") or []
        return [(float(c[0]), float(c[1])) for c in raw]
    return []
