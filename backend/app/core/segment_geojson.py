from __future__ import annotations

from typing import Any

from geoalchemy2.shape import to_shape

from app.db.models import NetworkSegment


def segment_to_feature(segment: NetworkSegment) -> dict[str, Any]:
    geom = to_shape(segment.geometry)
    coords = [[float(x), float(y)] for x, y in geom.coords]
    return {
        "type": "Feature",
        "properties": {
            "segment_id": segment.segment_id,
            "osm_way_id": segment.osm_way_id,
            "highway_type": segment.highway_type,
            "name": segment.name,
            "length_m": segment.length_m,
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
    }


def segments_to_feature_collection(
    segments: list[NetworkSegment],
    *,
    tile_id: str | None = None,
    total_in_tile: int | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    fc: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [segment_to_feature(s) for s in segments],
    }
    if tile_id is not None:
        fc["properties"] = {
            "tile_id": tile_id,
            "feature_count": len(segments),
            "total_in_tile": total_in_tile,
            "truncated": truncated,
        }
    return fc
