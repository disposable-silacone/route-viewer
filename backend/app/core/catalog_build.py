from __future__ import annotations

import os
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.osm_overpass import fetch_overpass_bbox
from app.core.osm_segments import ways_to_segment_drafts
from app.core.osm_types import OsmSegmentDraft
from app.db.catalog_tiles import CatalogTileRepository
from app.db.models import CatalogTile
from app.db.repositories import RegionRepository, SegmentRepository
from app.db.segment_ids import make_region_id, make_region_name


@dataclass
class TileBuildResult:
    tile_id: str
    status: str
    segments_fetched: int
    segments_upserted: int
    segment_count: int | None
    error: str | None = None


def _region_for_tile(db: Session, tile: CatalogTile) -> str:
    centroid_lat = (tile.bbox_min_lat + tile.bbox_max_lat) / 2.0
    centroid_lon = (tile.bbox_min_lon + tile.bbox_max_lon) / 2.0
    region_id = make_region_id(centroid_lat, centroid_lon)
    RegionRepository(db).upsert(
        region_id=region_id,
        name=make_region_name(centroid_lat, centroid_lon),
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        bbox_min_lat=tile.bbox_min_lat,
        bbox_min_lon=tile.bbox_min_lon,
        bbox_max_lat=tile.bbox_max_lat,
        bbox_max_lon=tile.bbox_max_lon,
    )
    return region_id


def build_catalog_tile(db: Session, tile_id: str) -> TileBuildResult:
    tile_repo = CatalogTileRepository(db)
    tile = tile_repo.get(tile_id)
    if not tile:
        return TileBuildResult(
            tile_id=tile_id,
            status="missing",
            segments_fetched=0,
            segments_upserted=0,
            segment_count=None,
            error="tile not found",
        )

    if tile.status == "ready":
        return TileBuildResult(
            tile_id=tile_id,
            status="ready",
            segments_fetched=0,
            segments_upserted=0,
            segment_count=tile.segment_count,
        )

    tile_repo.mark_building(tile_id)
    db.commit()

    try:
        data = fetch_overpass_bbox(
            min_lon=tile.fetch_min_lon,
            min_lat=tile.fetch_min_lat,
            max_lon=tile.fetch_max_lon,
            max_lat=tile.fetch_max_lat,
        )
        drafts = ways_to_segment_drafts(data.get("elements") or [])
        region_id = _region_for_tile(db, tile)
        upserted = SegmentRepository(db).upsert_drafts(drafts, region_id=region_id)
        segment_count = tile_repo.refresh_segment_count(tile_id)
        tile_repo.mark_ready(tile_id, segment_count=segment_count or 0)
        db.commit()
        return TileBuildResult(
            tile_id=tile_id,
            status="ready",
            segments_fetched=len(drafts),
            segments_upserted=upserted,
            segment_count=segment_count,
        )
    except Exception as exc:
        db.rollback()
        tile_repo.mark_failed(tile_id, str(exc))
        db.commit()
        return TileBuildResult(
            tile_id=tile_id,
            status="failed",
            segments_fetched=0,
            segments_upserted=0,
            segment_count=None,
            error=str(exc),
        )


def _inter_tile_delay_s() -> float:
    return max(0.0, float(os.getenv("CATALOG_BUILD_INTER_TILE_DELAY_S", "3")))


def build_catalog_tiles(db: Session, tile_ids: list[str]) -> list[TileBuildResult]:
    results: list[TileBuildResult] = []
    delay = _inter_tile_delay_s()
    for index, tile_id in enumerate(tile_ids):
        if index > 0 and delay > 0:
            time.sleep(delay)
        results.append(build_catalog_tile(db, tile_id))
    return results
