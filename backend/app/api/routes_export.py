from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
import json
from pathlib import Path
from app.db.session import SessionLocal
from app.db.models import Activity
from app.api.routes_ingest import LAST_SOURCE_DIR


router = APIRouter()


class ExportRequest(BaseModel):
    ids: list[str]
    format: str  # 'geojson' | 'svg'
    variant: str | None = None  # when 'geojson', 'matched' uses *_matched.json
    include: str | None = None  # when 'svg', 'matched' or 'raw'; default matched


@router.post("")
def export_routes(req: ExportRequest) -> Response:
    if req.format == "geojson":
        return _export_geojson(req)
    if req.format == "svg":
        return _export_svg(req)
    raise HTTPException(status_code=400, detail="unsupported format")


def _export_geojson(req: ExportRequest) -> Response:

    features = []
    with SessionLocal() as db:
        for act_id in req.ids:
            row = db.get(Activity, act_id)
            if not row or not row.geojson_path:
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


def _export_svg(req: ExportRequest) -> Response:
    # Collect matched (default) or raw line coordinates for selected ids
    paths: list[list[list[float]]] = []
    include = (req.include or "matched").lower()
    if include not in {"matched", "raw"}:
        include = "matched"
    with SessionLocal() as db:
        for act_id in req.ids:
            row = db.get(Activity, act_id)
            if not row or not row.geojson_path:
                continue
            p = Path(row.geojson_path)
            if include == "matched":
                alt = p.with_name(p.stem + "_matched.json")
                if alt.exists():
                    p = alt
            if not p.exists():
                continue
            fc = json.loads(p.read_text(encoding="utf-8"))
            for f in fc.get("features", []):
                if f.get("geometry", {}).get("type") == "LineString":
                    coords = f["geometry"].get("coordinates") or []
                    if coords:
                        paths.append(coords)
    if not paths:
        raise HTTPException(status_code=400, detail="no line data to export")

    # Compute bounds
    minx = min(c[0] for path in paths for c in path)
    miny = min(c[1] for path in paths for c in path)
    maxx = max(c[0] for path in paths for c in path)
    maxy = max(c[1] for path in paths for c in path)
    width_deg = maxx - minx
    height_deg = maxy - miny
    if width_deg <= 0 or height_deg <= 0:
        width_deg = height_deg = 1.0

    # Scale to a pixel canvas with padding so strokes are visible
    target = 1000.0  # px extent for the longer side
    pad = 20.0       # px padding on each side
    scale = target / max(width_deg, height_deg)
    out_w = width_deg * scale + 2 * pad
    out_h = height_deg * scale + 2 * pad

    # Project lon/lat into canvas space (linear, y inverted), add padding
    def project(pt: list[float]) -> tuple[float, float]:
        x = (pt[0] - minx) * scale + pad
        y = (maxy - pt[1]) * scale + pad
        return (x, y)

    # Build SVG
    stroke = "#1479ff"
    stroke_width = 2.0  # px
    lines: list[str] = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" version=\"1.1\" viewBox=\"0 0 {out_w:.0f} {out_h:.0f}\" stroke=\"{stroke}\" fill=\"none\" stroke-width=\"{stroke_width}\" stroke-linecap=\"round\" stroke-linejoin=\"round\">",
    ]
    for path in paths:
        d = " ".join(
            [
                ("M" if i == 0 else "L") + f"{project(pt)[0]:.1f},{project(pt)[1]:.1f}"
                for i, pt in enumerate(path)
            ]
        )
        lines.append(f"  <path d=\"{d}\" vector-effect=\"non-scaling-stroke\"/>")
    lines.append("</svg>")
    svg = "\n".join(lines)

    # Decide output directory: under last ingest path, subfolder 'exports'
    out_dir = (LAST_SOURCE_DIR or Path('.')).joinpath('exports')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "snapped.svg"
    out_path.write_text(svg, encoding="utf-8")

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": "attachment; filename=snapped.svg",
            "X-Export-Path": str(out_path),
        },
    )


