"""Unit tests for OSM segment extraction from Overpass JSON."""

from app.core.osm_segments import ways_to_segment_drafts
from app.db.segment_ids import make_segment_id


SAMPLE_OVERPASS = {
    "elements": [
        {"type": "node", "id": 1, "lat": 40.60, "lon": -75.50},
        {"type": "node", "id": 2, "lat": 40.601, "lon": -75.499},
        {"type": "node", "id": 3, "lat": 40.602, "lon": -75.498},
        {
            "type": "way",
            "id": 100,
            "nodes": [1, 2, 3],
            "tags": {
                "highway": "residential",
                "name": "Main St",
                "surface": "asphalt",
            },
        },
        {
            "type": "way",
            "id": 200,
            "nodes": [1, 2],
            "tags": {"highway": "motorway", "name": "I-78"},
        },
    ]
}


def test_ways_to_segment_drafts_splits_edges():
    drafts = ways_to_segment_drafts(SAMPLE_OVERPASS["elements"])
    assert len(drafts) == 2
    ids = {d.segment_id for d in drafts}
    assert make_segment_id(100, 1, 2) in ids
    assert make_segment_id(100, 2, 3) in ids


def test_ways_to_segment_drafts_skips_motorway():
    drafts = ways_to_segment_drafts(SAMPLE_OVERPASS["elements"])
    assert all(d.osm_way_id != 200 for d in drafts)


def test_segment_metadata():
    drafts = ways_to_segment_drafts(SAMPLE_OVERPASS["elements"])
    edge = next(d for d in drafts if d.osm_start_node_id == 1)
    assert edge.name == "Main St"
    assert edge.highway_type == "residential"
    assert edge.surface == "asphalt"
    assert edge.length_m > 0
