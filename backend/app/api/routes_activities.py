import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, select

from app.db.models import Activity
from app.db.segment_usage import SegmentUsageRepository
from app.db.session import SessionLocal


router = APIRouter()


@router.get("")
def list_activities(
    type: str | None = Query(None),
    customer_id: str | None = Query(None),
    region_id: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    minDist: int | None = Query(None),
    maxDist: int | None = Query(None),
    match_status: str | None = Query(None),
) -> list[dict]:
    with SessionLocal() as db:
        stmt = select(Activity)
        conditions = []
        if type:
            conditions.append(Activity.activity_type == type)
        if customer_id:
            conditions.append(Activity.customer_id == customer_id)
        if region_id:
            conditions.append(Activity.region_id == region_id)
        if start:
            from datetime import datetime
            conditions.append(Activity.started_at >= datetime.fromisoformat(start))
        if end:
            from datetime import datetime
            conditions.append(Activity.started_at <= datetime.fromisoformat(end))
        if minDist is not None:
            conditions.append(Activity.distance_m >= int(minDist))
        if maxDist is not None:
            conditions.append(Activity.distance_m <= int(maxDist))
        if match_status:
            conditions.append(Activity.match_status == match_status)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        rows = db.execute(stmt.order_by(Activity.started_at.asc())).scalars().all()
        return [
            {
                "id": r.activity_id,
                "customer_id": r.customer_id,
                "name": r.name,
                "source_file": Path(r.raw_file_path).name if r.raw_file_path else None,
                "type": r.activity_type,
                "region_id": r.region_id,
                "start": r.started_at.isoformat() if r.started_at else None,
                "distance_m": r.distance_m,
                "duration_sec": r.duration_s,
                "match_status": r.match_status,
                "match_confidence": r.match_confidence,
                "matched_at": r.matched_at.isoformat() if r.matched_at else None,
                "bbox": [float(x) for x in r.bbox.split(",")] if r.bbox else None,
            }
            for r in rows
        ]


@router.get("/{activity_id}/qa")
def get_activity_qa(activity_id: str) -> dict:
    with SessionLocal() as db:
        row = db.get(Activity, activity_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        diagnostics: dict = {}
        if row.match_diagnostics:
            try:
                diagnostics = json.loads(row.match_diagnostics)
            except json.JSONDecodeError:
                diagnostics = {}

        usage_repo = SegmentUsageRepository(db)
        usage_rows = usage_repo.list_for_activity(activity_id)
        unique_segments = diagnostics.get("unique_segments")
        if unique_segments is None and usage_rows:
            unique_segments = len(usage_rows)

        matched_distance_m = diagnostics.get("matched_distance_m")
        if matched_distance_m is None and usage_rows:
            matched_distance_m = sum(
                float(u.matched_length_m or 0.0) for u in usage_rows
            )

        return {
            "activity_id": activity_id,
            "match_status": row.match_status,
            "match_confidence": row.match_confidence,
            "raw_distance_m": row.distance_m,
            "matched_distance_m": matched_distance_m,
            "unique_segments": unique_segments,
            "segment_sequence_length": diagnostics.get("segment_sequence_length"),
            "low_support_segment_count": diagnostics.get("low_support_segment_count"),
            "suppressed_spur_count": diagnostics.get("suppressed_spur_count"),
            "weak_turn_reassignments": diagnostics.get("weak_turn_reassignments"),
            "matched_at": row.matched_at.isoformat() if row.matched_at else None,
        }


@router.get("/{activity_id}/segments")
def get_activity_segments(activity_id: str) -> dict:
    with SessionLocal() as db:
        row = db.get(Activity, activity_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        usage_repo = SegmentUsageRepository(db)
        rows = usage_repo.list_for_activity(activity_id)
        return {
            "activity_id": activity_id,
            "match_status": row.match_status,
            "match_confidence": row.match_confidence,
            "segment_count": len(rows),
            "segments": [
                {
                    "segment_id": u.segment_id,
                    "traversals": u.traversals,
                    "matched_length_m": u.matched_length_m,
                    "first_seen_order": u.first_seen_order,
                    "last_seen_order": u.last_seen_order,
                    "confidence": u.confidence,
                }
                for u in rows
            ],
        }


@router.get("/{activity_id}/geojson")
def get_activity_geojson(activity_id: str, variant: str | None = Query(None)) -> dict:
    with SessionLocal() as db:
        row = db.get(Activity, activity_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if not row.geojson_path:
            raise HTTPException(status_code=404, detail="geojson path not set")
        import json
        base = Path(row.geojson_path)
        if variant == "matched":
            p = base.with_name(base.stem + "_matched.json")
            if not p.exists():
                raise HTTPException(
                    status_code=404,
                    detail="matched geojson not found; run POST /mapmatch first",
                )
        else:
            p = base
            if not p.exists():
                raise HTTPException(status_code=404, detail="geojson not found")
        return json.loads(p.read_text(encoding="utf-8"))
