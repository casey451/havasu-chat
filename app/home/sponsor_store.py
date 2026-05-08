"""Sponsor lookup for the editorial slot (BUILD.md step 3).

Picks at most one active sponsor record per request. Active = ``active=True``
AND (``starts_at`` is null OR past) AND (``ends_at`` is null OR future).
When multiple rows are simultaneously active, the highest ``weight`` wins
(deterministic — random rotation is a future concern, not a launch one).

Returns a dict shaped to match the home template's expectations, or None
when no sponsor is active. The template's ``{% if sponsor %}`` branch
renders the fallback "Sponsor this slot →" card when None.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.models import Sponsor


def get_active_sponsor(db: Session) -> dict[str, Any] | None:
    """Return the active sponsor as a template-shaped dict, or None."""
    now = now_lake_havasu()
    row: Sponsor | None = (
        db.query(Sponsor)
        .filter(
            Sponsor.active.is_(True),
            or_(Sponsor.starts_at.is_(None), Sponsor.starts_at <= now),
            or_(Sponsor.ends_at.is_(None), Sponsor.ends_at > now),
        )
        .order_by(Sponsor.weight.desc(), Sponsor.created_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "eyebrow": row.eyebrow or "",
        "line": row.line or "",
        "cta_label": row.cta_label,
        "cta_url": row.cta_url,
        "image_url": row.image_url,
    }
