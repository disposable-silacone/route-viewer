from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OsmSegmentDraft:
    segment_id: str
    osm_way_id: int
    osm_start_node_id: int
    osm_end_node_id: int
    name: str | None
    highway_type: str | None
    surface: str | None
    access: str | None
    foot: str | None
    bicycle: str | None
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    length_m: float
