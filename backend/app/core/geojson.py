from __future__ import annotations

from pathlib import Path
import json
from typing import Iterable


def write_linestring_geojson(path: Path, coordinates: Iterable[tuple[float, float]], properties: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "LineString",
                    "coordinates": list(coordinates),
                },
            }
        ],
    }
    path.write_text(json.dumps(fc), encoding="utf-8")


