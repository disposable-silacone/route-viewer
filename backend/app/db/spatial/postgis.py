from __future__ import annotations

from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.spatial.base import SpatialBackend


class PostGISBackend(SpatialBackend):
    """PostGIS stub — ready for a future hosted / multi-user deployment."""

    @property
    def name(self) -> str:
        return "postgis"

    def init_connection(self, conn: Connection) -> None:
        # PostGIS extension is typically created once at database provisioning time.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

    def ensure_spatial_metadata(self, conn: Connection) -> None:
        return None

    def create_spatial_indexes(self, conn: Connection) -> None:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_network_segments_geometry "
                "ON network_segments USING GIST (geometry)"
            )
        )

    def geometry_type(self) -> Any:
        return Geometry(geometry_type="LINESTRING", srid=4326)

    def bbox_intersects_params(
        self,
        geometry_column: str,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> tuple[str, dict[str, float]]:
        sql = (
            f"ST_Intersects({geometry_column}, "
            f"ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
        )
        params = {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
        }
        return sql, params
