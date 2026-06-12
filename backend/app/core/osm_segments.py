from __future__ import annotations

from typing import Any

from app.core.geo import haversine_m
from app.core.osm_types import OsmSegmentDraft
from app.db.segment_ids import make_segment_id


# Match GraphHopper configs: skip motorway/trunk for pedestrian routing.
EXCLUDED_HIGHWAYS = frozenset(
    {
        "motorway",
        "motorway_link",
        "trunk",
        "trunk_link",
        "construction",
        "proposed",
        "abandoned",
        "razed",
    }
)


def _tag(tags: dict[str, str] | None, key: str) -> str | None:
    if not tags:
        return None
    value = tags.get(key)
    return value if value else None


def ways_to_segment_drafts(elements: list[dict[str, Any]]) -> list[OsmSegmentDraft]:
    """Convert Overpass elements to undirected OSM edge segments."""
    nodes: dict[int, tuple[float, float]] = {}
    for el in elements:
        if el.get("type") != "node":
            continue
        if "lat" not in el or "lon" not in el:
            continue
        nodes[int(el["id"])] = (float(el["lon"]), float(el["lat"]))

    drafts: list[OsmSegmentDraft] = []
    seen: set[str] = set()

    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        highway = tags.get("highway")
        if not highway or highway in EXCLUDED_HIGHWAYS:
            continue

        node_ids = [int(n) for n in el.get("nodes") or []]
        if len(node_ids) < 2:
            continue

        way_id = int(el["id"])
        name = _tag(tags, "name")
        surface = _tag(tags, "surface")
        access = _tag(tags, "access")
        foot = _tag(tags, "foot")
        bicycle = _tag(tags, "bicycle")

        for idx in range(len(node_ids) - 1):
            start_id = node_ids[idx]
            end_id = node_ids[idx + 1]
            start = nodes.get(start_id)
            end = nodes.get(end_id)
            if not start or not end:
                continue

            segment_id = make_segment_id(way_id, start_id, end_id)
            if segment_id in seen:
                continue
            seen.add(segment_id)

            start_lon, start_lat = start
            end_lon, end_lat = end
            length_m = haversine_m(start_lon, start_lat, end_lon, end_lat)
            if length_m <= 0:
                continue

            drafts.append(
                OsmSegmentDraft(
                    segment_id=segment_id,
                    osm_way_id=way_id,
                    osm_start_node_id=start_id,
                    osm_end_node_id=end_id,
                    name=name,
                    highway_type=highway,
                    surface=surface,
                    access=access,
                    foot=foot,
                    bicycle=bicycle,
                    start_lon=start_lon,
                    start_lat=start_lat,
                    end_lon=end_lon,
                    end_lat=end_lat,
                    length_m=length_m,
                )
            )

    return drafts
