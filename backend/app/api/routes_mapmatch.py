from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.catalog_match import (
    DEFAULT_SAMPLE_M,
    DEFAULT_SNAP_M,
    match_activity_from_geojson,
    write_matched_geojson,
)
from app.db.models import Activity
from app.db.session import SessionLocal


logger = logging.getLogger(__name__)

router = APIRouter()


class MapMatchRequest(BaseModel):
    ids: List[str]
    snapRadiusM: float | None = Field(default=None, alias="snapRadiusM")
    sampleIntervalM: float | None = Field(default=None, alias="sampleIntervalM")
    allowPartial: bool = Field(default=False, alias="allowPartial")
    writeGeojson: bool = Field(default=True, alias="writeGeojson")


def _result_dict(result) -> dict:
    return {
        "activity_id": result.activity_id,
        "status": result.status,
        "segment_count": result.segment_count,
        "points_sampled": result.points_sampled,
        "points_matched": result.points_matched,
        "points_unmatched": result.points_unmatched,
        "required_tiles": result.required_tiles,
        "ready_tiles": result.ready_tiles,
        "missing_tiles": result.missing_tiles,
        "not_ready_tiles": result.not_ready_tiles,
        "match_confidence": result.match_confidence,
        "error": result.error,
    }


@router.post("")
def map_match(req: MapMatchRequest) -> dict:
    """Snap activities to the global OSM catalog and write activity_segment_usage."""
    snap_m = req.snapRadiusM if req.snapRadiusM is not None else DEFAULT_SNAP_M
    sample_m = req.sampleIntervalM if req.sampleIntervalM is not None else DEFAULT_SAMPLE_M

    matched = 0
    partial = 0
    failed = 0
    results: list[dict] = []

    with SessionLocal() as db:
        for act_id in req.ids:
            row = db.get(Activity, act_id)
            if not row or not row.geojson_path:
                failed += 1
                results.append(
                    {"activity_id": act_id, "status": "failed", "error": "activity not found"}
                )
                continue

            raw_path = Path(row.geojson_path)
            if not raw_path.exists():
                failed += 1
                row.match_status = "failed"
                results.append(
                    {"activity_id": act_id, "status": "failed", "error": "geojson not found"}
                )
                continue

            logger.info(
                "Catalog match %s snap=%.0fm sample=%.0fm partial=%s",
                act_id,
                snap_m,
                sample_m,
                req.allowPartial,
            )

            result = match_activity_from_geojson(
                db,
                activity_id=act_id,
                geojson_path=raw_path,
                snap_radius_m=snap_m,
                sample_interval_m=sample_m,
                allow_partial=req.allowPartial,
            )

            if result.status == "matched":
                matched += 1
            elif result.status == "partial":
                partial += 1
            else:
                failed += 1
                activity = db.get(Activity, act_id)
                if activity:
                    activity.match_status = "failed"
                    activity.match_confidence = result.match_confidence

            if req.writeGeojson and result.matched_coords:
                out_path = raw_path.with_name(raw_path.stem + "_matched.json")
                write_matched_geojson(
                    out_path,
                    activity_id=act_id,
                    matched_coords=result.matched_coords,
                )

            results.append(_result_dict(result))

        db.commit()

    return {
        "ok": True,
        "matcher": "catalog",
        "matched": matched,
        "partial": partial,
        "failed": failed,
        "results": results,
    }
