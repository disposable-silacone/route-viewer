from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.engine import Connection


class SpatialBackend(ABC):
    """Database-neutral spatial operations.

    Application code should depend on this interface — not on SpatiaLite- or
    PostGIS-specific SQL scattered through routes and services.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def init_connection(self, conn: Connection) -> None:
        """Prepare a DBAPI connection (load extensions, etc.)."""
        ...

    @abstractmethod
    def ensure_spatial_metadata(self, conn: Connection) -> None:
        """Create spatial metadata tables if they do not exist."""
        ...

    @abstractmethod
    def create_spatial_indexes(self, conn: Connection) -> None:
        """Create spatial indexes after application tables exist."""
        ...

    @abstractmethod
    def geometry_type(self) -> Any:
        """Return the SQLAlchemy/GeoAlchemy geometry column type for linestrings."""
        ...

    @abstractmethod
    def bbox_intersects_params(
        self,
        geometry_column: str,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> tuple[str, dict[str, float]]:
        """Return (SQL fragment, bind params) testing geometry intersection with a bbox."""
        ...
