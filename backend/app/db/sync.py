from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Activity, ActivitySegmentUsage


def remove_stale_customer_activities(
    db: Session,
    customer_id: str,
    keep_hash_sigs: set[str],
) -> list[str]:
    """Delete this customer's activities not in the current batch (keeps global catalog)."""
    q = db.query(Activity).filter(Activity.customer_id == customer_id)
    if keep_hash_sigs:
        stale = q.filter(Activity.hash_sig.notin_(keep_hash_sigs)).all()
    else:
        stale = q.all()

    removed_ids: list[str] = []
    for act in stale:
        removed_ids.append(act.activity_id)
        db.query(ActivitySegmentUsage).filter(
            ActivitySegmentUsage.activity_id == act.activity_id
        ).delete()
        db.delete(act)
    return removed_ids
