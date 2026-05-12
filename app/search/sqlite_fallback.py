"""SQLite + dev-DB ILIKE fallback mirroring Tier 2 text match semantics.

Postgres production uses ``entities.search_vector``; tests run on SQLite where
the generated ``tsvector`` column does not exist. This module keeps the
LIKE-shaped path isolated (Phase 1A ``passive_deletes`` dialect-branch
precedent).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_synonyms import _category_needle_set


def _like_wrap(s: str | None) -> str | None:
    if not s or not str(s).strip():
        return None
    return f"%{str(s).strip()}%"


def build_ilike_entity_select(
    filters: Tier2Filters,
    *,
    entity_type: str | None = None,
    limit: int = 8,
):
    """Select active Entity rows using the Phase-2B.2 brief §6.4 ILIKE shape."""
    from app.db.models import Entity

    q = select(Entity).where(Entity.is_active.is_(True))
    if entity_type:
        q = q.where(Entity.entity_type == entity_type)
    if filters.entity_name and filters.entity_name.strip():
        needle = _like_wrap(filters.entity_name.strip())
        if needle:
            q = q.where(or_(Entity.name.ilike(needle), Entity.description.ilike(needle)))
    if filters.category and filters.category.strip():
        needles = _category_needle_set(filters.category)
        if needles:
            conds: list[Any] = []
            for n in needles:
                n_like = _like_wrap(n)
                if n_like:
                    conds.append(Entity.name.ilike(n_like))
                    conds.append(Entity.description.ilike(n_like))
            if conds:
                q = q.where(or_(*conds))
    return q.limit(limit)
