from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy import text

from app.db.models import Base
from app.db.session import apply_sql_migrations, engine
from app.db.spatial import get_spatial_backend


def initialize_database(db_engine: Engine, spatial=None) -> None:
    """Create application tables and spatial indexes."""
    backend = spatial or get_spatial_backend()

    with db_engine.connect() as conn:
        backend.init_connection(conn)
        backend.ensure_spatial_metadata(conn)
        conn.commit()

    Base.metadata.create_all(bind=db_engine)

    with db_engine.connect() as conn:
        backend.create_spatial_indexes(conn)
        conn.commit()


def _ensure_activity_cache_columns(db_engine: Engine) -> None:
    """Add presentation/cache columns to activities when upgrading from Task 1 schema."""
    columns = {
        "name": "TEXT",
        "activity_type": "TEXT",
        "geojson_path": "TEXT",
        "hash_sig": "TEXT",
        "bbox": "TEXT",
        "customer_id": "TEXT",
    }
    with db_engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(activities)")).fetchall()
        }
        for col, col_type in columns.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE activities ADD COLUMN {col} {col_type}"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_activities_customer_id "
                "ON activities (customer_id)"
            )
        )
        conn.commit()


def _drop_global_hash_sig_uniqueness(db_engine: Engine) -> None:
    """Remove legacy global unique on hash_sig; enforce per-customer uniqueness instead."""
    with db_engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_activities_hash_sig"))
        for row in conn.execute(text("PRAGMA index_list(activities)")).fetchall():
            idx_name = row[1]
            is_unique = row[2]
            if not is_unique:
                continue
            cols = [
                info[2]
                for info in conn.execute(
                    text(f'PRAGMA index_info("{idx_name}")')
                ).fetchall()
            ]
            if cols == ["hash_sig"]:
                conn.execute(text(f'DROP INDEX IF EXISTS "{idx_name}"'))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_activities_customer_hash "
                "ON activities (customer_id, hash_sig)"
            )
        )
        conn.commit()


def _backfill_legacy_customer_id(db_engine: Engine) -> None:
    """Assign pre-multi-customer rows so FK filters and stale sync work."""
    with db_engine.connect() as conn:
        null_count = conn.execute(
            text("SELECT COUNT(*) FROM activities WHERE customer_id IS NULL")
        ).scalar()
        if not null_count:
            return
        conn.execute(
            text(
                "INSERT OR IGNORE INTO customers (customer_id, name) "
                "VALUES ('_legacy', 'Pre-customer ingest')"
            )
        )
        conn.execute(
            text(
                "UPDATE activities SET customer_id = '_legacy' "
                "WHERE customer_id IS NULL"
            )
        )
        conn.commit()


def _ensure_match_qa_columns(db_engine: Engine) -> None:
    columns = {
        "matched_at": "DATETIME",
        "match_diagnostics": "TEXT",
    }
    with db_engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(activities)")).fetchall()
        }
        for col, col_type in columns.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE activities ADD COLUMN {col} {col_type}"))
        conn.commit()


def bootstrap_database(db_engine: Engine | None = None) -> None:
    """Initialize spatial metadata, ORM tables, spatial indexes, and SQL migrations."""
    target = db_engine or engine
    initialize_database(target)
    _ensure_activity_cache_columns(target)
    _ensure_match_qa_columns(target)
    apply_sql_migrations(target)
    _drop_global_hash_sig_uniqueness(target)
    _backfill_legacy_customer_id(target)
