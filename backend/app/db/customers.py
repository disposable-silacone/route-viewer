from __future__ import annotations

import re


_CUSTOMER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z0-9]$")


def normalize_customer_id(raw: str) -> str:
    """Normalize a customer slug for storage (lowercase, alphanumeric + hyphen/underscore)."""
    slug = raw.strip().lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-_")
    if not slug or not _CUSTOMER_ID_RE.match(slug):
        raise ValueError(
            "customerId must be 1–64 chars: lowercase letters, digits, hyphen, underscore"
        )
    return slug
