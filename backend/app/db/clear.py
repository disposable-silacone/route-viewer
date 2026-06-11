from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import (
    Activity,
    ActivitySegmentUsage,
    NetworkSegment,
    Region,
    SegmentStats,
)


def clear_ingest_data(db: Session) -> None:
    """Remove all ingest-derived rows in FK-safe order."""
    db.query(ActivitySegmentUsage).delete()
    db.query(SegmentStats).delete()
    db.query(NetworkSegment).delete()
    db.query(Activity).delete()
    db.query(Region).delete()
    db.commit()
