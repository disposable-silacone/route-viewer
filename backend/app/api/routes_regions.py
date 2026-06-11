from fastapi import APIRouter

from app.db.repositories import RegionRepository
from app.db.session import SessionLocal


router = APIRouter()


@router.get("")
def list_regions() -> list[dict]:
    with SessionLocal() as db:
        regions = RegionRepository(db).list_all()
        out: list[dict] = []
        for r in regions:
            activity_count = len(r.activities) if r.activities else 0
            out.append(
                {
                    "region_id": r.region_id,
                    "name": r.name,
                    "centroid": [r.centroid_lat, r.centroid_lon],
                    "bbox": [
                        r.bbox_min_lon,
                        r.bbox_min_lat,
                        r.bbox_max_lon,
                        r.bbox_max_lat,
                    ],
                    "activity_count": activity_count,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return out
