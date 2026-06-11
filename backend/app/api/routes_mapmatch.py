from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import os
import json
import requests
import logging
from typing import List
import math
from typing import List, Tuple

from app.db.session import SessionLocal
from app.db.models import Activity

logger = logging.getLogger(__name__)


router = APIRouter()


class MapMatchRequest(BaseModel):
    ids: List[str]
    profile: str = "bike"  # foot|bike|car
    gpsAccuracy: float | None = None  # meters; forwarded to GH as gps_accuracy


def _get_default_gps_accuracy(activity_type: str | None) -> float:
    """Get default GPS accuracy based on activity type and typical device characteristics.
    
    Returns accuracy in meters. Lower values = more precise matching.
    """
    if not activity_type:
        return 8.0  # Default fallback
    
    type_lower = activity_type.lower()
    
    # Garmin devices typically have good GPS accuracy
    if type_lower in ["run", "walk", "hike"]:
        return 30.0  # Increased further to allow more flexibility
    elif type_lower in ["ride", "bike", "cycling"]:
        return 35.0  # Increased further to allow more flexibility
    elif type_lower in ["swim"]:
        return 40.0  # Increased further to allow more flexibility
    else:
        return 35.0  # Increased further to allow more flexibility


def _coords_and_times_from_geojson(path: Path) -> tuple[List[List[float]], List[str] | None]:
    """Extract coordinates and timestamps from GeoJSON file.
    
    Returns:
        Tuple of (coordinates, timestamps) where coordinates are [lon, lat] 
        and timestamps are ISO format strings or None if not available.
    """
    fc = json.loads(path.read_text(encoding="utf-8"))
    features = fc.get("features") or []
    if not features:
        return [], None
    
    # Find the main LineString feature
    main_feature = None
    for f in features:
        if f.get("geometry", {}).get("type") == "LineString":
            main_feature = f
            break
    
    if not main_feature:
        return [], None
    
    coords = main_feature.get("geometry", {}).get("coordinates") or []
    if not coords:
        return [], None
    
    # Look for timestamp features (Point features with timestamp properties)
    timestamps = None
    for f in features:
        if (f.get("geometry", {}).get("type") == "Point" and 
            f.get("properties", {}).get("timestamp")):
            if timestamps is None:
                timestamps = [None] * len(coords)  # Initialize with None
            # Find matching coordinate and set timestamp
            point_coord = f["geometry"]["coordinates"]
            for i, coord in enumerate(coords):
                if coord == point_coord:
                    timestamps[i] = f["properties"]["timestamp"]
                    break
    
    return coords, timestamps


def _gpx_from_coords_and_times(coords: List[List[float]], timestamps: List[str] | None = None) -> str:
    """Generate GPX XML with coordinates and optional timestamps.
    
    Args:
        coords: List of [lon, lat] coordinates
        timestamps: Optional list of ISO format timestamp strings
    """
    # coords are [lon, lat]
    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<gpx version=\"1.1\" creator=\"route-viewer\" xmlns=\"http://www.topografix.com/GPX/1/1\">",
        "  <trk>",
        "    <name>activity</name>",
        "    <trkseg>",
    ]
    for i, (lon, lat) in enumerate(coords):
        if timestamps and i < len(timestamps) and timestamps[i]:
            lines.append(f"      <trkpt lat=\"{lat}\" lon=\"{lon}\"><time>{timestamps[i]}</time></trkpt>")
        else:
            lines.append(f"      <trkpt lat=\"{lat}\" lon=\"{lon}\"/>")
    lines += [
        "    </trkseg>",
        "  </trk>",
        "</gpx>",
    ]
    return "\n".join(lines)




def _cleanup_short_excursions(coords: List[List[float]], max_excursion_m: float = 50.0) -> List[List[float]]:
    """Remove short excursions that leave and return to the same road.
    
    This helps eliminate brief detours down side streets that don't add meaningful
    distance to the route.
    
    Args:
        coords: List of [lon, lat] coordinates
        max_excursion_m: Maximum excursion distance in meters to consider for removal
        
    Returns:
        Cleaned coordinates with short excursions removed
    """
    if len(coords) < 3:
        return coords
    
    def haversine_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """Calculate great-circle distance between two points in meters."""
        r = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c
    
    def point_to_line_distance(point: List[float], line_start: List[float], line_end: List[float]) -> float:
        """Calculate perpendicular distance from point to line segment."""
        px, py = point[0], point[1]
        x1, y1 = line_start[0], line_start[1]
        x2, y2 = line_end[0], line_end[1]
        
        # Vector from line_start to line_end
        dx = x2 - x1
        dy = y2 - y1
        
        # Check for zero-length line segment
        line_length_sq = dx * dx + dy * dy
        if line_length_sq == 0:
            # Line segment has zero length, return distance to either endpoint
            return haversine_distance(px, py, x1, y1)
        
        # Vector from line_start to point
        px_vec = px - x1
        py_vec = py - y1
        
        # Projection parameter
        t = max(0, min(1, (px_vec * dx + py_vec * dy) / line_length_sq))
        
        # Closest point on line segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        
        return haversine_distance(px, py, closest_x, closest_y)
    
    cleaned = [coords[0]]  # Always keep first point
    i = 1
    
    while i < len(coords) - 1:
        current = coords[i]
        next_point = coords[i + 1]
        
        # Check if this point creates a short excursion
        if i > 0:
            prev_point = coords[i - 1]
            
            # Calculate distance from current point to line between prev and next
            excursion_dist = point_to_line_distance(current, prev_point, next_point)
            
            # Calculate total distance of the excursion (prev -> current -> next)
            total_excursion = (haversine_distance(prev_point[0], prev_point[1], current[0], current[1]) + 
                             haversine_distance(current[0], current[1], next_point[0], next_point[1]))
            
            # Calculate direct distance (prev -> next)
            direct_dist = haversine_distance(prev_point[0], prev_point[1], next_point[0], next_point[1])
            
            # If excursion is short and doesn't add much distance, skip this point
            if (excursion_dist < max_excursion_m and 
                total_excursion - direct_dist < max_excursion_m * 2):
                i += 1
                continue
        
        cleaned.append(current)
        i += 1
    
    # Always keep last point
    if len(coords) > 1:
        cleaned.append(coords[-1])
    
    return cleaned


def _detect_state_from_coordinates(coords: List[List[float]]) -> str:
    """Detect which state the activity is in based on coordinates.
    
    Returns state code (PA, NY, NJ, FL) or 'PA' as default.
    """
    if not coords:
        return 'PA'  # Default fallback
    
    # Calculate center point
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    center_lon = sum(lons) / len(lons)
    center_lat = sum(lats) / len(lats)
    
    # Simple bounding box detection (approximate)
    # PA: ~-80.5 to -75, ~39.7 to 42.3
    if -80.5 <= center_lon <= -75 and 39.7 <= center_lat <= 42.3:
        return 'PA'
    # NY: ~-79.8 to -71.8, ~40.5 to 45.1
    elif -79.8 <= center_lon <= -71.8 and 40.5 <= center_lat <= 45.1:
        return 'NY'
    # NJ: ~-75.6 to -73.9, ~38.9 to 41.4
    elif -75.6 <= center_lon <= -73.9 and 38.9 <= center_lat <= 41.4:
        return 'NJ'
    # FL: ~-87.6 to -80, ~24.4 to 31.0
    elif -87.6 <= center_lon <= -80 and 24.4 <= center_lat <= 31.0:
        return 'FL'
    else:
        return 'PA'  # Default fallback


def _get_graphhopper_url_for_state(state: str) -> str:
    """Get GraphHopper server URL for the given state.
    
    Returns the appropriate GraphHopper server URL based on state.
    """
    # Map states to their GraphHopper server ports
    state_ports = {
        'PA': 8989,  # Default
        'NY': 8988,
        'NJ': 8987,
        'FL': 8986,
    }
    
    port = state_ports.get(state, 8989)
    return f"http://localhost:{port}"


@router.post("")
def map_match(req: MapMatchRequest) -> dict:
    matched = 0
    failed = 0

    with SessionLocal() as db:
        for act_id in req.ids:
            row = db.get(Activity, act_id)
            if not row or not row.geojson_path:
                failed += 1
                continue
            raw_path = Path(row.geojson_path)
            if not raw_path.exists():
                failed += 1
                continue

            coords, timestamps = _coords_and_times_from_geojson(raw_path)
            if not coords:
                failed += 1
                continue

            # Detect state and get appropriate GraphHopper server
            state = _detect_state_from_coordinates(coords)
            gh_base = _get_graphhopper_url_for_state(state)

            # Use provided GPS accuracy or default based on activity type
            gps_accuracy = req.gpsAccuracy
            if gps_accuracy is None:
                gps_accuracy = _get_default_gps_accuracy(row.activity_type)

            logger.info(f"Map-matching activity {act_id} with {len(coords)} points, profile={req.profile}, gps_accuracy={gps_accuracy}, state={state}, server={gh_base}")

            gpx_xml = _gpx_from_coords_and_times(coords, timestamps)
            try:
                url = f"{gh_base}/match?profile={req.profile}&type=json&points_encoded=false&debug=true&details=road_class&details=osm_way_id&gps_accuracy={gps_accuracy}"
                resp = requests.post(url, data=gpx_xml.encode("utf-8"), headers={"Content-Type": "application/gpx+xml"}, timeout=120)
                if resp.status_code >= 400:
                    failed += 1
                    continue
                data = resp.json()
                paths = data.get("paths") or []
                if not paths:
                    failed += 1
                    continue
                pts = paths[0].get("points") or {}
                out_coords = pts.get("coordinates") or []
                if not out_coords:
                    failed += 1
                    continue
                
                # Apply post-processing cleanup to remove short excursions
                original_count = len(out_coords)
                # Temporarily disable cleanup to see if basic map-matching works better
                cleaned_coords = out_coords  # _cleanup_short_excursions(out_coords, max_excursion_m=25.0)
                cleaned_count = len(cleaned_coords)
                
                # logger.info(f"Cleanup disabled - using original {cleaned_count} coordinates")
                
                details = paths[0].get("details") or {}
                snapped = data.get("snapped_waypoints") or None
                # Write matched GeoJSON next to raw
                out_path = raw_path.with_name(raw_path.stem + "_matched.json")
                fc = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"id": act_id, "variant": "matched", "profile_used": req.profile},
                            "geometry": {"type": "LineString", "coordinates": cleaned_coords},
                        }
                    ],
                }
                out_path.write_text(json.dumps(fc), encoding="utf-8")
                logger.info(f"Successfully map-matched activity {act_id}")
                matched += 1
            except Exception as e:
                logger.error(f"Failed to map-match activity {act_id}: {str(e)}")
                failed += 1
                continue

    return {"ok": True, "matched": matched, "failed": failed}


