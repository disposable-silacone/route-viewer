from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
import json
from pathlib import Path
from app.db.session import SessionLocal
from app.db.models import Activity


router = APIRouter()


class ExportRequest(BaseModel):
    ids: list[str]
    format: str
    variant: str | None = None


@router.post("")
def export_routes(req: ExportRequest) -> Response:
    if req.format not in {"geojson"}:
        raise HTTPException(status_code=400, detail="only 'geojson' supported currently")

    features = []
    with SessionLocal() as db:
        for act_id in req.ids:
            row = db.get(Activity, act_id)
            if not row:
                continue
            p = Path(row.geojson_path)
            if req.variant == "matched":
                alt = p.with_name(p.stem + "_matched.json")
                if alt.exists():
                    p = alt
            if not p.exists():
                continue
            fc = json.loads(p.read_text(encoding="utf-8"))
            feats = fc.get("features", [])
            features.extend(feats)

    merged = {"type": "FeatureCollection", "features": features}
    payload = json.dumps(merged)
    return Response(
        content=payload,
        media_type="application/geo+json",
        headers={
            "Content-Disposition": "attachment; filename=export.geojson"
        },
    )


