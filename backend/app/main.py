from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path

# Routers
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_activities import router as activities_router
from app.api.routes_export import router as export_router
from app.api.routes_mapmatch import router as mapmatch_router
from app.api.routes_inspect import router as inspect_router
from app.api.routes_regions import router as regions_router
from app.api.routes_catalog import router as catalog_router
from app.api.routes_customers import router as customers_router
from app.api.routes_segments import router as segments_router
from app.db.migrate import bootstrap_database


def create_app() -> FastAPI:
    app = FastAPI(title="Route Viewer Backend", version="0.1.0")

    # CORS (frontend default vite dev origin plus local file origins)
    vite_origin = os.getenv("VITE_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[vite_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Ensure data/cache directories exist
    data_dir = Path(os.getenv("DATA_CACHE_DIR", ".cache"))
    db_path = Path(os.getenv("DB_PATH", ".data/app.db"))
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Routers
    app.include_router(health_router)
    app.include_router(ingest_router, prefix="/ingest", tags=["ingest"])
    app.include_router(activities_router, prefix="/activities", tags=["activities"])
    app.include_router(export_router, prefix="/export", tags=["export"])
    app.include_router(mapmatch_router, prefix="/mapmatch", tags=["mapmatch"])
    app.include_router(inspect_router, prefix="/inspect", tags=["inspect"])
    app.include_router(regions_router, prefix="/regions", tags=["regions"])
    app.include_router(catalog_router, prefix="/catalog", tags=["catalog"])
    app.include_router(customers_router, prefix="/customers", tags=["customers"])
    app.include_router(segments_router, prefix="/segments", tags=["segments"])

    @app.on_event("startup")
    def _create_tables() -> None:
        bootstrap_database()

    return app


app = create_app()


