from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, and_
from app.db.session import SessionLocal
from app.db.models import Activity
from pathlib import Path


router = APIRouter()


@router.get("")
def list_activities(
    type: str | None = Query(None),
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
        if start:
            from datetime import datetime
            conditions.append(Activity.start_time_utc >= datetime.fromisoformat(start))
        if end:
            from datetime import datetime
            conditions.append(Activity.end_time_utc <= datetime.fromisoformat(end))
        if minDist is not None:
            conditions.append(Activity.distance_m >= int(minDist))
        if maxDist is not None:
            conditions.append(Activity.distance_m <= int(maxDist))
        if conditions:
            stmt = stmt.where(and_(*conditions))

        rows = db.execute(stmt.order_by(Activity.start_time_utc.asc())).scalars().all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "source_file": Path(r.source_path).name if r.source_path else None,
                "type": r.activity_type,
                "start": r.start_time_utc.isoformat() if r.start_time_utc else None,
                "end": r.end_time_utc.isoformat() if r.end_time_utc else None,
                "distance_m": r.distance_m,
                "duration_sec": r.duration_sec,
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
        import json
        from pathlib import Path
        base = Path(row.geojson_path)
        p = base
        if variant == "matched":
            p = base.with_name(base.stem + "_matched.json")
        if not p.exists():
            # fallback to raw if matched not present
            p = base
        if not p.exists():
            raise HTTPException(status_code=404, detail="geojson not found")
        return json.loads(p.read_text(encoding="utf-8"))


