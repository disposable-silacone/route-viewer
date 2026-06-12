from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog_tiles import (
    TileConfig,
    TileRef,
    get_tile_config,
    parse_bbox_string,
    tiles_for_coordinates,
    tiles_for_stored_bbox,
)
from app.db.models import Activity, CatalogTile
from app.db.repositories import SegmentRepository

TileStatus = Literal["pending", "building", "ready", "failed"]


class CatalogTileRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, tile_id: str) -> CatalogTile | None:
        return self._db.get(CatalogTile, tile_id)

    def register_required(
        self,
        tiles: list[TileRef],
    ) -> dict[str, int]:
        """Upsert tiles as pending unless already building or ready."""
        counts = {"new": 0, "existing": 0, "skipped_ready": 0}
        for ref in tiles:
            row = self.get(ref.tile_id)
            if row:
                counts["existing"] += 1
                if row.status in ("ready", "building"):
                    counts["skipped_ready"] += 1
                continue
            self._db.add(self._row_from_ref(ref, status="pending"))
            counts["new"] += 1
        self._db.flush()
        return counts

    def list_all(
        self,
        *,
        status: str | None = None,
        tile_scheme: str | None = None,
    ) -> list[CatalogTile]:
        stmt = select(CatalogTile).order_by(CatalogTile.created_at)
        if status:
            stmt = stmt.where(CatalogTile.status == status)
        if tile_scheme:
            stmt = stmt.where(CatalogTile.tile_scheme == tile_scheme)
        return list(self._db.scalars(stmt).all())

    def required_tiles_for_customer(
        self,
        customer_id: str,
        *,
        config: TileConfig | None = None,
    ) -> list[TileRef]:
        cfg = config or get_tile_config()
        activities = list(
            self._db.scalars(
                select(Activity).where(Activity.customer_id == customer_id)
            ).all()
        )
        seen: dict[str, TileRef] = {}
        for activity in activities:
            refs = self._tiles_for_activity(activity, config=cfg)
            for ref in refs:
                if ref.tile_scheme == cfg.tile_scheme:
                    seen[ref.tile_id] = ref
        return list(seen.values())

    def coverage_for_customer(
        self,
        customer_id: str,
        *,
        config: TileConfig | None = None,
    ) -> dict:
        cfg = config or get_tile_config()
        required = self.required_tiles_for_customer(customer_id, config=cfg)
        return self._coverage_summary(required, cfg)

    def coverage_for_tile_ids(
        self,
        tile_ids: list[str],
        *,
        config: TileConfig | None = None,
    ) -> dict:
        cfg = config or get_tile_config()
        rows = {
            row.tile_id: row
            for row in self._db.scalars(
                select(CatalogTile).where(CatalogTile.tile_id.in_(tile_ids))
            ).all()
        }
        return self._coverage_from_ids(tile_ids, rows, cfg)

    def list_buildable(
        self,
        *,
        limit: int = 1,
        tile_scheme: str | None = None,
        status: TileStatus = "pending",
    ) -> list[CatalogTile]:
        return self.list_buildable_statuses(
            limit=limit,
            tile_scheme=tile_scheme,
            statuses=[status],
        )

    def list_buildable_statuses(
        self,
        *,
        limit: int = 1,
        tile_scheme: str | None = None,
        statuses: list[TileStatus] | tuple[TileStatus, ...] = ("failed", "pending"),
    ) -> list[CatalogTile]:
        """Return up to `limit` tiles, preferring earlier statuses (failed before pending)."""
        cfg = get_tile_config()
        scheme = tile_scheme or cfg.tile_scheme
        picked: list[CatalogTile] = []
        for status in statuses:
            if len(picked) >= limit:
                break
            stmt = (
                select(CatalogTile)
                .where(CatalogTile.status == status)
                .order_by(CatalogTile.updated_at.asc())
                .limit(max(1, limit - len(picked)))
            )
            if scheme:
                stmt = stmt.where(CatalogTile.tile_scheme == scheme)
            picked.extend(self._db.scalars(stmt).all())
        return picked[:limit]

    def mark_building(self, tile_id: str) -> CatalogTile | None:
        row = self.get(tile_id)
        if not row:
            return None
        row.status = "building"
        row.error_message = None
        row.updated_at = datetime.utcnow()
        return row

    def mark_ready(self, tile_id: str, *, segment_count: int) -> CatalogTile | None:
        row = self.get(tile_id)
        if not row:
            return None
        row.status = "ready"
        row.segment_count = segment_count
        row.built_at = datetime.utcnow()
        row.error_message = None
        row.updated_at = datetime.utcnow()
        return row

    def mark_failed(self, tile_id: str, error: str) -> CatalogTile | None:
        row = self.get(tile_id)
        if not row:
            return None
        row.status = "failed"
        row.error_message = error[:2000]
        row.updated_at = datetime.utcnow()
        return row

    def refresh_segment_count(self, tile_id: str) -> int | None:
        """Diagnostic: count global segments intersecting the tile core bbox."""
        row = self.get(tile_id)
        if not row:
            return None
        count = SegmentRepository(self._db).count_in_bbox(
            min_lon=row.bbox_min_lon,
            min_lat=row.bbox_min_lat,
            max_lon=row.bbox_max_lon,
            max_lat=row.bbox_max_lat,
            region_id=None,
        )
        row.segment_count = count
        row.updated_at = datetime.utcnow()
        return count

    def _tiles_for_activity(
        self,
        activity: Activity,
        *,
        config: TileConfig,
    ) -> list[TileRef]:
        if activity.geojson_path:
            try:
                import json
                from pathlib import Path

                data = json.loads(Path(activity.geojson_path).read_text(encoding="utf-8"))
                coords = _coords_from_geojson(data)
                if coords:
                    return tiles_for_coordinates(coords, config=config)
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass

        bbox = parse_bbox_string(activity.bbox)
        if bbox:
            return tiles_for_stored_bbox(bbox, config=config)
        return []

    def _coverage_summary(self, required: list[TileRef], cfg: TileConfig) -> dict:
        tile_ids = [ref.tile_id for ref in required]
        rows = {
            row.tile_id: row
            for row in self._db.scalars(
                select(CatalogTile).where(CatalogTile.tile_id.in_(tile_ids))
            ).all()
        } if tile_ids else {}
        summary = self._coverage_from_ids(tile_ids, rows, cfg)
        summary["tiles"] = [
            self._tile_coverage_row(ref, rows.get(ref.tile_id))
            for ref in sorted(required, key=lambda r: r.tile_id)
        ]
        return summary

    def _coverage_from_ids(
        self,
        tile_ids: list[str],
        rows: dict[str, CatalogTile],
        cfg: TileConfig,
    ) -> dict:
        by_status: dict[str, int] = {
            "pending": 0,
            "building": 0,
            "ready": 0,
            "failed": 0,
            "missing": 0,
        }
        for tile_id in tile_ids:
            row = rows.get(tile_id)
            if not row:
                by_status["missing"] += 1
            else:
                by_status[row.status] = by_status.get(row.status, 0) + 1

        required = len(tile_ids)
        ready = by_status["ready"]
        return {
            "customer_id": None,
            "tile_scheme": cfg.tile_scheme,
            "catalog_version": cfg.catalog_version,
            "tile_km": cfg.tile_km,
            "activity_buffer_km": cfg.activity_buffer_km,
            "fetch_margin_m": cfg.fetch_margin_m,
            "required_tiles": required,
            "ready_tiles": ready,
            "catalog_complete": required > 0 and ready == required,
            "counts_by_status": by_status,
        }

    def _tile_coverage_row(
        self,
        ref: TileRef,
        row: CatalogTile | None,
    ) -> dict:
        status = row.status if row else "missing"
        return {
            "tile_id": ref.tile_id,
            "lat_idx": ref.lat_idx,
            "lon_idx": ref.lon_idx,
            "status": status,
            "segment_count": row.segment_count if row else None,
            "error_message": row.error_message if row else None,
            "bbox": list(ref.bbox),
            "fetch_bbox": list(ref.fetch_bbox),
        }

    @staticmethod
    def _row_from_ref(ref: TileRef, *, status: TileStatus) -> CatalogTile:
        min_lon, min_lat, max_lon, max_lat = ref.bbox
        fmin_lon, fmin_lat, fmax_lon, fmax_lat = ref.fetch_bbox
        cfg = get_tile_config()
        return CatalogTile(
            tile_id=ref.tile_id,
            tile_scheme=ref.tile_scheme,
            catalog_version=ref.catalog_version,
            lat_idx=ref.lat_idx,
            lon_idx=ref.lon_idx,
            bbox_min_lon=min_lon,
            bbox_min_lat=min_lat,
            bbox_max_lon=max_lon,
            bbox_max_lat=max_lat,
            fetch_min_lon=fmin_lon,
            fetch_min_lat=fmin_lat,
            fetch_max_lon=fmax_lon,
            fetch_max_lat=fmax_lat,
            fetch_margin_m=cfg.fetch_margin_m,
            status=status,
        )


def _coords_from_geojson(data: dict) -> list[tuple[float, float]]:
    geom = data.get("geometry") or data
    gtype = geom.get("type")
    coords_raw = geom.get("coordinates")
    if not coords_raw:
        return []
    if gtype == "LineString":
        return [(float(c[0]), float(c[1])) for c in coords_raw]
    if gtype == "MultiLineString":
        out: list[tuple[float, float]] = []
        for line in coords_raw:
            out.extend((float(c[0]), float(c[1])) for c in line)
        return out
    return []
