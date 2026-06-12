from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.catalog_build import build_catalog_tiles
from app.core.catalog_tiles import get_tile_config
from app.core.segment_geojson import segments_to_feature_collection
from app.db.catalog_tiles import CatalogTileRepository
from app.db.customers import normalize_customer_id
from app.db.repositories import SegmentRepository
from app.db.session import SessionLocal


router = APIRouter()


def _tile_row(row) -> dict:
    return {
        "tile_id": row.tile_id,
        "tile_scheme": row.tile_scheme,
        "catalog_version": row.catalog_version,
        "lat_idx": row.lat_idx,
        "lon_idx": row.lon_idx,
        "status": row.status,
        "segment_count": row.segment_count,
        "bbox": [
            row.bbox_min_lon,
            row.bbox_min_lat,
            row.bbox_max_lon,
            row.bbox_max_lat,
        ],
        "fetch_bbox": [
            row.fetch_min_lon,
            row.fetch_min_lat,
            row.fetch_max_lon,
            row.fetch_max_lat,
        ],
        "fetch_margin_m": row.fetch_margin_m,
        "built_at": row.built_at.isoformat() if row.built_at else None,
        "error_message": row.error_message,
    }


@router.get("/tiles")
def list_catalog_tiles(
    status: str | None = Query(None),
    tile_scheme: str | None = Query(None),
) -> dict:
    cfg = get_tile_config()
    with SessionLocal() as db:
        repo = CatalogTileRepository(db)
        rows = repo.list_all(
            status=status,
            tile_scheme=tile_scheme or cfg.tile_scheme,
        )
        return {
            "tile_scheme": tile_scheme or cfg.tile_scheme,
            "catalog_version": cfg.catalog_version,
            "tiles": [_tile_row(r) for r in rows],
        }


@router.get("/coverage")
def catalog_coverage(
    customer_id: str = Query(..., alias="customerId"),
) -> dict:
    try:
        normalized = normalize_customer_id(customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cfg = get_tile_config()
    with SessionLocal() as db:
        repo = CatalogTileRepository(db)
        summary = repo.coverage_for_customer(normalized, config=cfg)
        summary["customer_id"] = normalized
        return summary


@router.get("/tiles/{tile_id}")
def get_catalog_tile(tile_id: str) -> dict:
    with SessionLocal() as db:
        repo = CatalogTileRepository(db)
        row = repo.get(tile_id)
        if not row:
            raise HTTPException(status_code=404, detail="tile not found")
        return _tile_row(row)


@router.get("/tiles/{tile_id}/summary")
def catalog_tile_summary(tile_id: str) -> dict:
    with SessionLocal() as db:
        tile_repo = CatalogTileRepository(db)
        tile = tile_repo.get(tile_id)
        if not tile:
            raise HTTPException(status_code=404, detail="tile not found")

        seg_repo = SegmentRepository(db)
        by_highway = seg_repo.highway_summary_in_bbox(
            min_lon=tile.bbox_min_lon,
            min_lat=tile.bbox_min_lat,
            max_lon=tile.bbox_max_lon,
            max_lat=tile.bbox_max_lat,
        )
        return {
            "tile_id": tile.tile_id,
            "status": tile.status,
            "segment_count": tile.segment_count,
            "bbox": [
                tile.bbox_min_lon,
                tile.bbox_min_lat,
                tile.bbox_max_lon,
                tile.bbox_max_lat,
            ],
            "highway_types": [
                {"highway_type": hw or "unknown", "count": count}
                for hw, count in by_highway
            ],
        }


@router.get("/tiles/{tile_id}/geojson")
def catalog_tile_geojson(
    tile_id: str,
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    with SessionLocal() as db:
        tile_repo = CatalogTileRepository(db)
        tile = tile_repo.get(tile_id)
        if not tile:
            raise HTTPException(status_code=404, detail="tile not found")
        if tile.status != "ready":
            raise HTTPException(
                status_code=400,
                detail=f"tile status is {tile.status!r}; build it first",
            )

        seg_repo = SegmentRepository(db)
        total = tile.segment_count or seg_repo.count_in_bbox(
            min_lon=tile.bbox_min_lon,
            min_lat=tile.bbox_min_lat,
            max_lon=tile.bbox_max_lon,
            max_lat=tile.bbox_max_lat,
        )
        segments = seg_repo.sample_in_bbox(
            min_lon=tile.bbox_min_lon,
            min_lat=tile.bbox_min_lat,
            max_lon=tile.bbox_max_lon,
            max_lat=tile.bbox_max_lat,
            limit=limit,
        )
        return segments_to_feature_collection(
            segments,
            tile_id=tile_id,
            total_in_tile=total,
            truncated=total > len(segments),
        )


class CatalogBuildRequest(BaseModel):
    tileIds: list[str] | None = Field(default=None, alias="tileIds")
    customerId: str | None = Field(default=None, alias="customerId")
    limit: int = 1
    status: str = "pending"
    statuses: list[str] | None = Field(default=None, alias="statuses")


def _build_statuses(req: CatalogBuildRequest) -> list[str]:
    if req.statuses:
        return req.statuses
    if req.status == "failed":
        return ["failed"]
    if req.status == "pending":
        return ["failed", "pending"]
    return [req.status]


@router.post("/build")
def build_catalog(req: CatalogBuildRequest) -> dict:
    if req.limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if req.limit > 20:
        raise HTTPException(status_code=400, detail="limit must be <= 20")

    cfg = get_tile_config()
    build_statuses = _build_statuses(req)
    with SessionLocal() as db:
        repo = CatalogTileRepository(db)

        tile_ids: list[str] = []
        if req.tileIds:
            tile_ids = req.tileIds
        elif req.customerId:
            try:
                customer_id = normalize_customer_id(req.customerId)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            required = repo.required_tiles_for_customer(customer_id, config=cfg)
            rows = {
                row.tile_id: row
                for row in repo.list_all(tile_scheme=cfg.tile_scheme)
            }
            for status in build_statuses:
                for ref in required:
                    row = rows.get(ref.tile_id)
                    tile_status = row.status if row else "missing"
                    if tile_status == status or (tile_status == "missing" and status == "pending"):
                        if ref.tile_id not in tile_ids:
                            tile_ids.append(ref.tile_id)
                    if len(tile_ids) >= req.limit:
                        break
                if len(tile_ids) >= req.limit:
                    break
            tile_ids = tile_ids[: req.limit]
        else:
            rows = repo.list_buildable_statuses(
                limit=req.limit,
                tile_scheme=cfg.tile_scheme,
                statuses=build_statuses,  # type: ignore[arg-type]
            )
            tile_ids = [row.tile_id for row in rows]

        if not tile_ids:
            return {
                "built": 0,
                "results": [],
                "message": "no matching tiles to build",
            }

        results = build_catalog_tiles(db, tile_ids)
        return {
            "built": len(results),
            "results": [
                {
                    "tile_id": r.tile_id,
                    "status": r.status,
                    "segments_fetched": r.segments_fetched,
                    "segments_upserted": r.segments_upserted,
                    "segment_count": r.segment_count,
                    "error": r.error,
                }
                for r in results
            ],
        }
