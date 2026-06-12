from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import ActivitySegmentUsage


@dataclass(frozen=True)
class UsageDraft:
    segment_id: str
    traversals: int
    matched_length_m: float
    first_seen_order: int
    last_seen_order: int
    confidence: float


class SegmentUsageRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_activity(self, activity_id: str) -> list[ActivitySegmentUsage]:
        return list(
            self._db.scalars(
                select(ActivitySegmentUsage)
                .where(ActivitySegmentUsage.activity_id == activity_id)
                .order_by(ActivitySegmentUsage.first_seen_order.asc())
            ).all()
        )

    def replace_for_activity(
        self,
        activity_id: str,
        rows: list[UsageDraft],
    ) -> int:
        self._db.execute(
            delete(ActivitySegmentUsage).where(
                ActivitySegmentUsage.activity_id == activity_id
            )
        )
        for row in rows:
            self._db.add(
                ActivitySegmentUsage(
                    activity_id=activity_id,
                    segment_id=row.segment_id,
                    traversals=row.traversals,
                    matched_length_m=row.matched_length_m,
                    first_seen_order=row.first_seen_order,
                    last_seen_order=row.last_seen_order,
                    confidence=row.confidence,
                )
            )
        self._db.flush()
        return len(rows)
