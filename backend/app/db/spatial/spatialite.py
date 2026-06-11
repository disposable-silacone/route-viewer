from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from geoalchemy2 import Geometry
from geoalchemy2.types import WKBElement
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.spatial.base import SpatialBackend


def _ensure_dll_search_path(extension: str) -> str:
    """Make dependency DLLs discoverable on Windows before load_extension."""
    ext_path = Path(extension)
    if ext_path.suffix.lower() == ".dll" and ext_path.is_file():
        dll_dir = str(ext_path.parent.resolve())
        extension = str(ext_path.resolve())
    else:
        bin_dir = os.getenv("SPATIALITE_BIN_DIR")
        dll_dir = str(Path(bin_dir).resolve()) if bin_dir else None

    if dll_dir:
        if sys.platform == "win32":
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        else:
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(dll_dir)
            except OSError:
                pass

    return extension


def load_spatialite_dbapi(dbapi_conn) -> None:
    """Load mod_spatialite on a raw sqlite3 connection."""
    extension = _ensure_dll_search_path(
        os.getenv("SPATIALITE_EXTENSION", "mod_spatialite")
    )
    dbapi_conn.enable_load_extension(True)
    dbapi_conn.load_extension(extension)
    dbapi_conn.enable_load_extension(False)


class SpatiaLiteBackend(SpatialBackend):
    """SpatiaLite implementation for local MVP / batch processing."""

    @property
    def name(self) -> str:
        return "spatialite"

    def init_connection(self, conn: Connection) -> None:
        load_spatialite_dbapi(conn.connection.dbapi_connection)

    def ensure_spatial_metadata(self, conn: Connection) -> None:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='geometry_columns'"
            )
        ).scalar_one()
        if int(row) == 0:
            conn.execute(text("SELECT InitSpatialMetaData(1)"))

    def create_spatial_indexes(self, conn: Connection) -> None:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='idx_network_segments_geometry'"
            )
        ).scalar_one()
        if int(exists) == 0:
            conn.execute(
                text(
                    "SELECT CreateSpatialIndex('network_segments', 'geometry')"
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
        # MBRIntersects is efficient for bbox pre-filtering in SpatiaLite.
        sql = (
            f"MBRIntersects({geometry_column}, "
            f"BuildMBR(:min_lon, :min_lat, :max_lon, :max_lat))"
        )
        params = {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
        }
        return sql, params


def geometry_to_wkt(element: WKBElement | None) -> str | None:
    """Convert a GeoAlchemy WKBElement to WKT via SpatiaLite function name."""
    if element is None:
        return None
    # Shapely is already a project dependency; keep decoding out of SQL dialect code.
    from shapely import wkb

    return wkb.loads(bytes(element.data)).wkt
