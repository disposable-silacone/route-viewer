from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import os
import json
import requests
from typing import List

from app.db.session import SessionLocal
from app.db.models import Activity


router = APIRouter()


class MapMatchRequest(BaseModel):
    ids: List[str]
    profile: str = "bike"  # foot|bike|car
    gpsAccuracy: float | None = None  # meters; forwarded to GH as gps_accuracy


def _coords_from_geojson(path: Path) -> List[List[float]]:
    fc = json.loads(path.read_text(encoding="utf-8"))
    features = fc.get("features") or []
    if not features:
        return []
    geom = features[0].get("geometry") or {}
    if geom.get("type") == "LineString":
        return geom.get("coordinates") or []
    return []


def _gpx_from_coords(coords: List[List[float]]) -> str:
    # coords are [lon, lat]
    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<gpx version=\"1.1\" creator=\"route-viewer\" xmlns=\"http://www.topografix.com/GPX/1/1\">",
        "  <trk>",
        "    <name>activity</name>",
        "    <trkseg>",
    ]
    for lon, lat in coords:
        lines.append(f"      <trkpt lat=\"{lat}\" lon=\"{lon}\"/>")
    lines += [
        "    </trkseg>",
        "  </trk>",
        "</gpx>",
    ]
    return "\n".join(lines)


@router.post("")
def map_match(req: MapMatchRequest) -> dict:
    gh_base = os.getenv("GRAPHOPPER_BASE_URL", "http://localhost:8989")
    matched = 0
    failed = 0

    with SessionLocal() as db:
        for act_id in req.ids:
            row = db.get(Activity, act_id)
            if not row:
                failed += 1
                continue
            raw_path = Path(row.geojson_path)
            if not raw_path.exists():
                failed += 1
                continue

            coords = _coords_from_geojson(raw_path)
            if not coords:
                failed += 1
                continue

            gpx_xml = _gpx_from_coords(coords)
            try:
                url = f"{gh_base}/match?profile={req.profile}&type=json&points_encoded=false&debug=true&details=road_class&details=osm_way_id"
                if req.gpsAccuracy is not None:
                    url += f"&gps_accuracy={req.gpsAccuracy}"
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
                # points might be {"type":"LineString","coordinates":[[lon,lat],...]}
                out_coords = pts.get("coordinates") or []
                if not out_coords:
                    failed += 1
                    continue
                details = paths[0].get("details") or {}
                snapped = data.get("snapped_waypoints") or None
                # Write matched GeoJSON next to raw
                out_path = raw_path.with_name(raw_path.stem + "_matched.json")
                fc = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"id": act_id, "variant": "matched", "profile": req.profile, "details": details, "snapped_waypoints": snapped},
                            "geometry": {"type": "LineString", "coordinates": out_coords},
                        }
                    ],
                }
                out_path.write_text(json.dumps(fc), encoding="utf-8")
                matched += 1
            except Exception:
                failed += 1
                continue

    return {"ok": True, "matched": matched, "failed": failed}


