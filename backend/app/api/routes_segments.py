from fastapi import APIRouter, HTTPException

from app.core.segment_geojson import segment_to_feature
from app.db.repositories import SegmentRepository
from app.db.session import SessionLocal


router = APIRouter()


@router.get("/{segment_id}/geojson")
def get_segment_geojson(segment_id: str) -> dict:
    with SessionLocal() as db:
        segment = SegmentRepository(db).get(segment_id)
        if not segment:
            raise HTTPException(status_code=404, detail="segment not found")
        return segment_to_feature(segment)
