from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import hashlib
import os
import shutil

from app.core.ingest_paths import collect_ingest_paths
from app.core.parse_activity import parse_activity
from app.core.geojson import write_linestring_geojson
from app.core.geo import bbox_to_string, compute_bbox
from app.core.region_cluster import (
    ActivityDraft,
    cluster_drafts,
    draft_from_track,
    merge_clusters_by_region_id,
    region_bbox_for_cluster,
)
from app.db.customers import normalize_customer_id
from app.db.session import SessionLocal
from app.db.models import Activity
from app.db.repositories import CustomerRepository, RegionRepository
from app.db.sync import remove_stale_customer_activities
from app.db.segment_ids import make_activity_id, make_region_id, make_region_name
from app.core.catalog_tiles import TileRef, tiles_for_coordinates, get_tile_config
from app.db.catalog_tiles import CatalogTileRepository


router = APIRouter()

DEFAULT_CLUSTER_KM = float(os.getenv("REGION_CLUSTER_KM", "10"))


def _get_cache_root() -> Path:
    env_dir = os.getenv("DATA_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    win_local = os.getenv("LOCALAPPDATA")
    if win_local:
        return Path(win_local) / "RouteViewer" / "cache"
    return Path(".cache")


PROGRESS: dict = {
    "started": False,
    "done": False,
    "total": 0,
    "scanned": 0,
    "parsed": 0,
    "new": 0,
    "updated": 0,
    "removed": 0,
    "duplicates": 0,
    "errors": 0,
    "regions": 0,
    "current": None,
}

LAST_SOURCE_DIR: Path | None = None


@router.get("/progress")
def get_progress() -> dict:
    return PROGRESS


class IngestRequest(BaseModel):
    sourceUri: str
    customerId: str
    customerName: str | None = None


def _content_hash(track, bbox: tuple[float, float, float, float]) -> str:
    rounded_start = track.start_time_utc.replace(second=0, microsecond=0)
    rounded_dist = (track.distance_m // 10) * 10
    sig_src = (
        f"{rounded_start.isoformat()}|{rounded_dist}|"
        f"{track.activity_type}|{','.join(map(str, bbox))}"
    )
    return hashlib.sha1(sig_src.encode("utf-8")).hexdigest()


def _upsert_activity(
    db,
    *,
    customer_id: str,
    draft: ActivityDraft,
    region_id: str,
    geojson_path: Path,
) -> tuple[Activity, bool]:
    """Return (activity, is_new)."""
    track = draft.track
    existing = db.get(Activity, draft.activity_id)
    if existing:
        existing.source = draft.source_format
        existing.source_activity_id = draft.file_path.stem
        existing.started_at = track.start_time_utc
        existing.distance_m = float(track.distance_m)
        existing.duration_s = track.duration_sec
        existing.region_id = region_id
        existing.raw_file_path = str(draft.file_path)
        existing.name = track.name or draft.file_path.stem
        existing.activity_type = track.activity_type or "unknown"
        existing.geojson_path = str(geojson_path)
        existing.hash_sig = draft.hash_sig
        existing.bbox = bbox_to_string(draft.bbox)
        return existing, False

    activity = Activity(
        activity_id=draft.activity_id,
        customer_id=customer_id,
        source=draft.source_format,
        source_activity_id=draft.file_path.stem,
        started_at=track.start_time_utc,
        distance_m=float(track.distance_m),
        duration_s=track.duration_sec,
        region_id=region_id,
        raw_file_path=str(draft.file_path),
        match_status="pending",
        name=track.name or draft.file_path.stem,
        activity_type=track.activity_type or "unknown",
        geojson_path=str(geojson_path),
        hash_sig=draft.hash_sig,
        bbox=bbox_to_string(draft.bbox),
    )
    db.add(activity)
    return activity, True


@router.post("")
def ingest(req: IngestRequest) -> dict:
    try:
        customer_id = normalize_customer_id(req.customerId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    path = Path(req.sourceUri.replace("file://", ""))
    if not path.exists():
        raise HTTPException(status_code=400, detail="sourceUri does not exist")

    cache_root = _get_cache_root()
    cache_dir = cache_root / "geojson" / customer_id
    extract_dir = cache_root / "ingest_extract"
    shutil.rmtree(extract_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    scanned = 0
    parsed = 0
    new = 0
    updated = 0
    removed = 0
    duplicates = 0
    errors = 0

    PROGRESS.update(
        {
            "started": True,
            "done": False,
            "total": 0,
            "scanned": 0,
            "parsed": 0,
            "new": 0,
            "updated": 0,
            "removed": 0,
            "duplicates": 0,
            "errors": 0,
            "regions": 0,
            "current": None,
        }
    )

    global LAST_SOURCE_DIR
    LAST_SOURCE_DIR = path if path.is_dir() else path.parent

    candidates: list[Path] = collect_ingest_paths(path, extract_dir)
    PROGRESS["total"] = len(candidates)

    drafts: list[ActivityDraft] = []
    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()
    batch_hashes: set[str] = set()

    for f in candidates:
        try:
            PROGRESS["current"] = str(f)
            scanned += 1
            PROGRESS["scanned"] = scanned

            parsed_track, source_format = parse_activity(f)
            if not parsed_track or parsed_track.distance_m <= 0 or not parsed_track.coordinates:
                continue

            parsed += 1
            PROGRESS["parsed"] = parsed

            file_key = str(f.resolve())
            if file_key in seen_paths:
                duplicates += 1
                PROGRESS["duplicates"] = duplicates
                continue
            seen_paths.add(file_key)

            bbox = compute_bbox(parsed_track.coordinates)
            hash_sig = _content_hash(parsed_track, bbox)
            if hash_sig in seen_hashes:
                duplicates += 1
                PROGRESS["duplicates"] = duplicates
                continue
            seen_hashes.add(hash_sig)
            batch_hashes.add(hash_sig)

            act_id = make_activity_id(customer_id, hash_sig)
            drafts.append(
                draft_from_track(
                    activity_id=act_id,
                    file_path=f,
                    source_format=source_format,
                    track=parsed_track,
                    hash_sig=hash_sig,
                )
            )
        except Exception:
            errors += 1
            PROGRESS["errors"] = errors

    clusters = merge_clusters_by_region_id(
        cluster_drafts(drafts, threshold_km=DEFAULT_CLUSTER_KM)
    )
    region_summaries: list[dict] = []
    required_tiles: dict[str, TileRef] = {}

    with SessionLocal() as db:
        customer_repo = CustomerRepository(db)
        customer_repo.get_or_create(
            customer_id,
            name=req.customerName or customer_id,
        )
        region_repo = RegionRepository(db)

        removed_ids = remove_stale_customer_activities(db, customer_id, batch_hashes)
        removed = len(removed_ids)
        PROGRESS["removed"] = removed
        for act_id in removed_ids:
            stale_path = cache_dir / f"{act_id}.json"
            stale_path.unlink(missing_ok=True)
            matched_path = cache_dir / f"{act_id}_matched.json"
            matched_path.unlink(missing_ok=True)

        for cluster in sorted(
            clusters,
            key=lambda c: (-len(c.members), c.centroid_lat, c.centroid_lon),
        ):
            rbbox = region_bbox_for_cluster(cluster)
            min_lon, min_lat, max_lon, max_lat = rbbox
            region_id = make_region_id(cluster.centroid_lat, cluster.centroid_lon)

            region = region_repo.upsert(
                region_id=region_id,
                name=make_region_name(cluster.centroid_lat, cluster.centroid_lon),
                centroid_lat=cluster.centroid_lat,
                centroid_lon=cluster.centroid_lon,
                bbox_min_lat=min_lat,
                bbox_min_lon=min_lon,
                bbox_max_lat=max_lat,
                bbox_max_lon=max_lon,
            )

            for draft in cluster.members:
                track = draft.track
                geojson_path = cache_dir / f"{draft.activity_id}.json"
                write_linestring_geojson(
                    geojson_path,
                    track.coordinates,
                    {
                        "id": draft.activity_id,
                        "name": track.name or draft.file_path.stem,
                        "type": track.activity_type,
                        "region_id": region.region_id,
                        "customer_id": customer_id,
                    },
                    timestamps=track.timestamps,
                )

                _, is_new = _upsert_activity(
                    db,
                    customer_id=customer_id,
                    draft=draft,
                    region_id=region.region_id,
                    geojson_path=geojson_path,
                )
                if is_new:
                    new += 1
                    PROGRESS["new"] = new
                else:
                    updated += 1
                    PROGRESS["updated"] = updated

                for tile_ref in tiles_for_coordinates(
                    track.coordinates, config=get_tile_config()
                ):
                    required_tiles[tile_ref.tile_id] = tile_ref

            region_summaries.append(
                {
                    "region_id": region.region_id,
                    "name": region.name,
                    "centroid": [region.centroid_lat, region.centroid_lon],
                    "bbox": [min_lon, min_lat, max_lon, max_lat],
                    "activity_count": len(cluster.members),
                }
            )

        tile_repo = CatalogTileRepository(db)
        tile_registration = tile_repo.register_required(list(required_tiles.values()))

        db.commit()

    tile_cfg = get_tile_config()
    catalog_summary = {
        "tile_scheme": tile_cfg.tile_scheme,
        "catalog_version": tile_cfg.catalog_version,
        "required_tiles": len(required_tiles),
        **tile_registration,
    }

    PROGRESS["regions"] = len(clusters)
    PROGRESS.update({"done": True, "current": None})

    return {
        "customerId": customer_id,
        "summary": {
            "scanned": scanned,
            "parsed": parsed,
            "new": new,
            "updated": updated,
            "removed": removed,
            "duplicates": duplicates,
            "errors": errors,
            "regions": len(clusters),
            "cluster_threshold_km": DEFAULT_CLUSTER_KM,
        },
        "regions": region_summaries,
        "catalog": catalog_summary,
        "batchId": None,
    }
