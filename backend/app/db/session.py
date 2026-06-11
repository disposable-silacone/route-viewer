from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.db.spatial import get_spatial_backend


def get_database_url() -> str:
    backend = os.getenv("SPATIAL_BACKEND", "spatialite").lower()
    db_path = os.getenv("DB_PATH", ".data/app.db")

    if backend == "postgis":
        return os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://routeviewer:routeviewer@localhost:5432/routeviewer",
        )

    return f"sqlite:///{db_path}"


def create_engine_with_spatial() -> Engine:
    backend_name = os.getenv("SPATIAL_BACKEND", "spatialite").lower()
    url = get_database_url()

    if backend_name == "spatialite":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
        )
    else:
        engine = create_engine(url)

    return engine


engine = create_engine_with_spatial()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _register_spatialite_loader(db_engine: Engine) -> None:
    if os.getenv("SPATIAL_BACKEND", "spatialite").lower() != "spatialite":
        return

    from app.db.spatial.spatialite import load_spatialite_dbapi

    @event.listens_for(db_engine, "connect")
    def _load_spatialite(dbapi_connection, connection_record) -> None:
        try:
            load_spatialite_dbapi(dbapi_connection)
        except Exception as exc:
            raise RuntimeError(
                "Failed to load SpatiaLite extension. Set SPATIALITE_EXTENSION to the "
                "full path of mod_spatialite.dll (all archive DLLs in the same folder)."
            ) from exc


_register_spatialite_loader(engine)


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    for part in sql.split(";"):
        stmt = part.strip()
        if not stmt or stmt.startswith("--"):
            continue
        lines = [
            line for line in stmt.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        cleaned = "\n".join(lines).strip()
        if cleaned:
            statements.append(cleaned)
    return statements


def apply_sql_migrations(engine: Engine) -> None:
    migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
    if not migrations_dir.exists():
        return

    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  version TEXT PRIMARY KEY,"
                "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
                ")"
            )
        )
        conn.commit()

    for path in sorted(migrations_dir.glob("*.sql")):
        version = path.stem
        with engine.connect() as conn:
            applied = conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE version = :v"),
                {"v": version},
            ).first()
            if applied:
                continue
            sql = path.read_text(encoding="utf-8")
            for stmt in _split_sql_statements(sql):
                conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:v)"),
                {"v": version},
            )
            conn.commit()
