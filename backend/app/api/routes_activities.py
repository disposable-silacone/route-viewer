from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, and_
from app.db.session import SessionLocal
from app.db.models import Activity
from pathlib import Path


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
                "bbox": [float(x) for x in r.bbox.split(",")] if r.bbox else None,
            }
            for r in rows
        ]


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
        p = base
        if variant == "matched":
            p = base.with_name(base.stem + "_matched.json")
        if not p.exists():
            p = base
        if not p.exists():
            raise HTTPException(status_code=404, detail="geojson not found")
        return json.loads(p.read_text(encoding="utf-8"))
