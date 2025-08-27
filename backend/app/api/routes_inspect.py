from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Optional, List, Tuple
import os
import math
import requests


router = APIRouter()


def _dest_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> Tuple[float, float]:
    # Simple equirectangular approximation good for short distances
    r = 6371000.0
    br = math.radians(bearing_deg)
    d_r = distance_m / r
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) + math.cos(lat1) * d_r * math.cos(br))
    lon2 = lon1 + d_r * math.sin(br) / max(math.cos(lat1), 1e-9)
    return (math.degrees(lat2), math.degrees(lon2))


def _route_details(gh_base: str, lat: float, lon: float, profile: str) -> dict:
    # Use a tiny segment to force path details on the nearest edge
    eps_lat, eps_lon = _dest_point(lat, lon, 45.0, 3.0)
    url = (
        f"{gh_base}/route?point={lat},{lon}&point={eps_lat},{eps_lon}"
        f"&type=json&points_encoded=false&ch.disable=true&profile={profile}"
        f"&details=road_class&details=osm_way_id&locale=en"
    )
    try:
        r = requests.get(url, timeout=30)
        if r.status_code >= 400:
            return {}
        js = r.json()
        paths = js.get("paths") or []
        if not paths:
            return {}
        p0 = paths[0]
        return {
            "details": p0.get("details") or {},
            "snapped": js.get("snapped_waypoints") or p0.get("snapped_waypoints"),
            "points": p0.get("points") or {},
        }
    except Exception:
        return {}


@router.get("")
def inspect(
    lat: float = Query(...),
    lon: float = Query(...),
    profile: str = Query("bike"),
    radius: float = Query(30.0),
    samples: int = Query(16),
) -> dict:
    gh_base = os.getenv("GRAPHOPPER_BASE_URL", "http://localhost:8989")

    main = _route_details(gh_base, lat, lon, profile)

    # Sample around the point to approximate nearby candidate edges
    cand_pts: List[List[float]] = []  # [lon, lat]
    total = max(4, min(64, samples))
    for i in range(total):
        br = (360.0 * i) / total
        s_lat, s_lon = _dest_point(lat, lon, br, radius)
        det = _route_details(gh_base, s_lat, s_lon, profile)
        snapped = det.get("snapped")
        if isinstance(snapped, dict):
            coords = snapped.get("coordinates") or []
            if coords:
                cand_pts.append(coords[0])

    features = []
    # Center clicked point
    features.append({
        "type": "Feature",
        "properties": {"kind": "center"},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    })
    # Snapped point (center)
    main_snapped = main.get("snapped")
    if isinstance(main_snapped, dict):
        coords = main_snapped.get("coordinates") or []
        if coords:
            features.append({
                "type": "Feature",
                "properties": {"kind": "snapped_center"},
                "geometry": {"type": "Point", "coordinates": coords[0]},
            })
    # Candidate snapped samples
    for c in cand_pts:
        features.append({
            "type": "Feature",
            "properties": {"kind": "candidate"},
            "geometry": {"type": "Point", "coordinates": c},
        })

    # Attach a tiny polyline along the nearest edge for context
    pts = (main.get("points") or {}).get("coordinates") or []
    if pts:
        features.append({
            "type": "Feature",
            "properties": {"kind": "edge"},
            "geometry": {"type": "LineString", "coordinates": pts},
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"details": main.get("details") or {}},
    }


