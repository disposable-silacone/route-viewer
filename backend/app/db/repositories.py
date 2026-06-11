from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Customer, NetworkSegment, Region
from app.db.segment_ids import make_region_id, make_region_name
from app.db.spatial import SpatialBackend, get_spatial_backend


class CustomerRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, customer_id: str) -> Customer | None:
        return self._db.get(Customer, customer_id)

    def get_or_create(self, customer_id: str, name: str | None = None) -> Customer:
        row = self.get(customer_id)
        if row:
            if name and row.name != name:
                row.name = name
            return row
        row = Customer(customer_id=customer_id, name=name or customer_id)
        self._db.add(row)
        self._db.flush()
        return row


class RegionRepository:
    def __init__(self, db: Session, spatial: SpatialBackend | None = None) -> None:
        self._db = db
        self._spatial = spatial or get_spatial_backend()

    def get(self, region_id: str) -> Region | None:
        return self._db.get(Region, region_id)

    def create(
        self,
        *,
        name: str | None,
        centroid_lat: float,
        centroid_lon: float,
        bbox_min_lat: float,
        bbox_min_lon: float,
        bbox_max_lat: float,
        bbox_max_lon: float,
        region_id: str | None = None,
    ) -> Region:
        row = Region(
            region_id=region_id or make_region_id(centroid_lat, centroid_lon),
            name=name,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
            bbox_min_lat=bbox_min_lat,
            bbox_min_lon=bbox_min_lon,
            bbox_max_lat=bbox_max_lat,
            bbox_max_lon=bbox_max_lon,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def upsert(
        self,
        *,
        region_id: str,
        centroid_lat: float,
        centroid_lon: float,
        bbox_min_lat: float,
        bbox_min_lon: float,
        bbox_max_lat: float,
        bbox_max_lon: float,
        name: str | None = None,
    ) -> Region:
        row = self.get(region_id)
        display_name = name or make_region_name(centroid_lat, centroid_lon)
        if row:
            row.name = display_name
            row.centroid_lat = centroid_lat
            row.centroid_lon = centroid_lon
            row.bbox_min_lat = min(row.bbox_min_lat, bbox_min_lat)
            row.bbox_min_lon = min(row.bbox_min_lon, bbox_min_lon)
            row.bbox_max_lat = max(row.bbox_max_lat, bbox_max_lat)
            row.bbox_max_lon = max(row.bbox_max_lon, bbox_max_lon)
            row.updated_at = datetime.utcnow()
            return row
        return self.create(
            region_id=region_id,
            name=display_name,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
            bbox_min_lat=bbox_min_lat,
            bbox_min_lon=bbox_min_lon,
            bbox_max_lat=bbox_max_lat,
            bbox_max_lon=bbox_max_lon,
        )

    def list_all(self) -> list[Region]:
        return list(self._db.scalars(select(Region).order_by(Region.created_at)).all())


class SegmentRepository:
    def __init__(self, db: Session, spatial: SpatialBackend | None = None) -> None:
        self._db = db
        self._spatial = spatial or get_spatial_backend()

    def get(self, segment_id: str) -> NetworkSegment | None:
        return self._db.get(NetworkSegment, segment_id)

    def find_in_bbox(
        self,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        region_id: str | None = None,
    ) -> list[NetworkSegment]:
        clause, params = self._spatial.bbox_intersects_params(
            "network_segments.geometry",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        sql = f"SELECT segment_id FROM network_segments WHERE {clause}"
        if region_id:
            sql += " AND region_id = :region_id"
            params["region_id"] = region_id

        rows = self._db.execute(text(sql), params).all()
        ids = [row[0] for row in rows]
        if not ids:
            return []
        return list(
            self._db.scalars(
                select(NetworkSegment).where(NetworkSegment.segment_id.in_(ids))
            ).all()
        )

    def count_in_bbox(
        self,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        region_id: str | None = None,
    ) -> int:
        clause, params = self._spatial.bbox_intersects_params(
            "network_segments.geometry",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        sql = f"SELECT COUNT(*) FROM network_segments WHERE {clause}"
        if region_id:
            sql += " AND region_id = :region_id"
            params["region_id"] = region_id
        return int(self._db.execute(text(sql), params).scalar_one())

    def catalog_covers_bbox(
        self,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        region_id: str | None = None,
        min_segment_count: int = 1,
    ) -> bool:
        """Diagnostic helper — prefer catalog_tiles.status for coverage gates."""
        return (
            self.count_in_bbox(
                min_lon=min_lon,
                min_lat=min_lat,
                max_lon=max_lon,
                max_lat=max_lat,
                region_id=region_id,
            )
            >= min_segment_count
        )
