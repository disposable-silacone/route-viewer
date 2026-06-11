from __future__ import annotations

import os

from app.db.spatial.base import SpatialBackend
from app.db.spatial.postgis import PostGISBackend
from app.db.spatial.spatialite import SpatiaLiteBackend

_BACKENDS: dict[str, SpatialBackend] = {
    "spatialite": SpatiaLiteBackend(),
    "postgis": PostGISBackend(),
}


def get_spatial_backend(name: str | None = None) -> SpatialBackend:
    key = (name or os.getenv("SPATIAL_BACKEND", "spatialite")).lower()
    try:
        return _BACKENDS[key]
    except KeyError as exc:
        supported = ", ".join(sorted(_BACKENDS))
        raise ValueError(
            f"Unknown spatial backend {key!r}. Supported: {supported}"
        ) from exc
