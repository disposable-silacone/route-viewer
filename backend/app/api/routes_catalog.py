from fastapi import APIRouter, HTTPException, Query

from app.core.catalog_tiles import get_tile_config
from app.db.catalog_tiles import CatalogTileRepository
from app.db.customers import normalize_customer_id
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
