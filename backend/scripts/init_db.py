#!/usr/bin/env python3
"""Initialize the Route Viewer geospatial database."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as `python scripts/init_db.py` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.migrate import bootstrap_database  # noqa: E402
from app.db.session import engine  # noqa: E402


def main() -> None:
    db_path = Path(os.getenv("DB_PATH", ".data/app.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"Initializing database at {db_path} "
        f"(backend={os.getenv('SPATIAL_BACKEND', 'spatialite')})"
    )
    bootstrap_database(engine)
    print("Done.")


if __name__ == "__main__":
    main()
