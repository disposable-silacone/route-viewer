from __future__ import annotations

from pathlib import Path
import json
from typing import Iterable, Optional, List, Tuple
from datetime import datetime


def write_linestring_geojson(
    path: Path, 
    coordinates: Iterable[tuple[float, float]], 
    properties: dict,
    timestamps: Optional[List[datetime]] = None,
    elevations: Optional[List[float]] = None
) -> None:
    """Write a LineString GeoJSON with optional timestamps and elevations.
    
    Args:
        path: Output file path
        coordinates: List of (lon, lat) tuples
        properties: Feature properties
        timestamps: Optional list of datetime objects for each coordinate
        elevations: Optional list of elevation values for each coordinate
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build coordinate array with optional metadata
    coords_list = list(coordinates)
    coord_features = []
    
    for i, (lon, lat) in enumerate(coords_list):
        coord_props = {}
        if timestamps and i < len(timestamps):
            coord_props["timestamp"] = timestamps[i].isoformat()
        if elevations and i < len(elevations):
            coord_props["elevation"] = elevations[i]
        
        if coord_props:
            coord_features.append({
                "type": "Feature",
                "properties": coord_props,
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                }
            })
    
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords_list,
                },
            }
        ],
    }
    
    # Add coordinate metadata as additional features if present
    if coord_features:
        fc["features"].extend(coord_features)
    
    path.write_text(json.dumps(fc), encoding="utf-8")


