from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import uuid
from datetime import datetime
import hashlib
import os
import shutil

from app.core.walker import iter_candidate_files
from app.core.parse_gpx import parse_gpx_file
from app.core.parse_fit import parse_fit_file
from app.core.geojson import write_linestring_geojson
from app.db.session import SessionLocal, engine
from app.db.models import Activity, Base
from sqlalchemy import select


router = APIRouter()


def _get_cache_root() -> Path:
    """Choose a cache root outside OneDrive by default on Windows.

    Honors DATA_CACHE_DIR if set; otherwise uses %LOCALAPPDATA%/RouteViewer/cache
    when available, and falls back to .cache in the current working directory.
    """
    env_dir = os.getenv("DATA_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    win_local = os.getenv("LOCALAPPDATA")
    if win_local:
        return Path(win_local) / "RouteViewer" / "cache"
    return Path(".cache")


# Simple in-process ingest progress state
PROGRESS: dict = {
    "started": False,
    "done": False,
    "total": 0,
    "scanned": 0,
    "parsed": 0,
    "new": 0,
    "duplicates": 0,
    "errors": 0,
    "current": None,
}

# Remember the most recent ingest source directory so other endpoints
# (e.g., export) can write outputs adjacent to the user's data.
LAST_SOURCE_DIR: Path | None = None


@router.get("/progress")
def get_progress() -> dict:
    return PROGRESS


class IngestRequest(BaseModel):
    sourceUri: str


@router.post("")
def ingest(req: IngestRequest) -> dict:
    path = Path(req.sourceUri.replace("file://", ""))
    if not path.exists():
        raise HTTPException(status_code=400, detail="sourceUri does not exist")

    # Reset DB and cached geojson on each ingest to reflect only the provided folder
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    except Exception:
        # If drop/create fails, fall back to deleting rows
        with SessionLocal() as db:
            db.query(Activity).delete()
            db.commit()

    cache_root = _get_cache_root()
    cache_dir = cache_root / "geojson"
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    scanned = 0
    parsed = 0
    new = 0
    duplicates = 0
    errors = 0

    # initialize progress
    PROGRESS.update({
        "started": True,
        "done": False,
        "total": 0,
        "scanned": 0,
        "parsed": 0,
        "new": 0,
        "duplicates": 0,
        "errors": 0,
        "current": None,
    })

    # Persist where the user pointed ingest so exports can write nearby
    global LAST_SOURCE_DIR
    LAST_SOURCE_DIR = path if path.is_dir() else path.parent

    with SessionLocal() as db:
        candidates = []
        if path.is_file():
            candidates = [path]
        else:
            candidates = list(iter_candidate_files(path))

        PROGRESS["total"] = len(candidates)
        for f in candidates:
            try:
                PROGRESS["current"] = str(f)
                PROGRESS["scanned"] = PROGRESS.get("scanned", 0) + 1
                if f.suffix.lower() == ".gpx":
                    parsed_track = parse_gpx_file(f)
                elif f.suffix.lower() == ".fit":
                    parsed_track = parse_fit_file(f)
                else:
                    parsed_track = None
                if not parsed_track or parsed_track.distance_m <= 0 or not parsed_track.coordinates:
                    continue
                parsed += 1
                PROGRESS["parsed"] = parsed

                bbox = compute_bbox(parsed_track.coordinates)
                rounded_start = parsed_track.start_time_utc.replace(second=0, microsecond=0)
                dist_val = parsed_track.distance_m or 0
                rounded_dist = (dist_val // 10) * 10
                sig_src = f"{rounded_start.isoformat()}|{rounded_dist}|{parsed_track.activity_type}|{','.join(map(str,bbox))}"
                hash_sig = hashlib.sha1(sig_src.encode("utf-8")).hexdigest()

                # Skip if this file/path was already ingested
                existing_by_path = db.execute(select(Activity).where(Activity.source_path == str(f))).scalar_one_or_none()
                if existing_by_path:
                    duplicates += 1
                    PROGRESS["duplicates"] = duplicates
                    continue

                exists = db.execute(select(Activity).where(Activity.hash_sig == hash_sig)).scalar_one_or_none()
                if exists:
                    duplicates += 1
                    PROGRESS["duplicates"] = duplicates
                    continue

                act_id = str(uuid.uuid4())
                geojson_path = cache_dir / f"{act_id}.json"
                write_linestring_geojson(geojson_path, parsed_track.coordinates, {
                    "id": act_id,
                    "name": parsed_track.name or f.stem,
                    "type": parsed_track.activity_type,
                }, timestamps=parsed_track.timestamps)

                activity = Activity(
                    id=act_id,
                    source_path=str(f),
                    source_format="GPX" if f.suffix.lower() == ".gpx" else "FIT",
                    activity_type=parsed_track.activity_type or "unknown",
                    name=parsed_track.name or f.stem,
                    start_time_utc=parsed_track.start_time_utc,
                    end_time_utc=parsed_track.end_time_utc,
                    duration_sec=parsed_track.duration_sec,
                    distance_m=parsed_track.distance_m,
                    elev_gain_m=parsed_track.elev_gain_m,
                    avg_hr=None,
                    max_hr=None,
                    polyline_points=None,
                    geojson_path=str(geojson_path),
                    bbox=",".join(map(str, bbox)),
                    hash_sig=hash_sig,
                    ingested_at=datetime.utcnow(),
                )
                db.add(activity)
                db.commit()
                new += 1
                PROGRESS["new"] = new
            except Exception:
                errors += 1
                PROGRESS["errors"] = errors
                continue

    PROGRESS.update({"done": True, "current": None})
    return {
        "summary": {"scanned": scanned, "parsed": parsed, "new": new, "duplicates": duplicates, "errors": errors},
        "batchId": None,
    }


def compute_bbox(coords: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    if not coords:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return (min(xs), min(ys), max(xs), max(ys))


