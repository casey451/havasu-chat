"""User favorites — Phase 2A.3."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session as SqlSession
from sqlalchemy.orm import joinedload

from app.db.entity_types import (
    ENTITY_TYPE_COMMERCIAL,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_PLACE,
)
from app.db.models import Entity, UserFavorite


def entity_is_favoritable(entity_type: str) -> bool:
    return entity_type in (ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE, ENTITY_TYPE_EVENT)


def toggle_favorite(
    db: SqlSession, user_id: str, entity_id: str
) -> tuple[Literal["added", "removed"], int]:
    existing = (
        db.query(UserFavorite)
        .filter(UserFavorite.user_id == user_id, UserFavorite.entity_id == entity_id)
        .first()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()
        action: Literal["added", "removed"] = "removed"
    else:
        db.add(UserFavorite(user_id=user_id, entity_id=entity_id))
        db.flush()
        action = "added"
    cnt = db.query(func.count(UserFavorite.id)).filter(UserFavorite.user_id == user_id).scalar()
    return action, int(cnt or 0)


def list_user_favorites(db: SqlSession, user_id: str) -> list[Entity]:
    rows = (
        db.query(UserFavorite)
        .options(joinedload(UserFavorite.entity))
        .filter(UserFavorite.user_id == user_id)
        .order_by(UserFavorite.created_at.desc())
        .all()
    )
    return [r.entity for r in rows if r.entity is not None]


def is_favorited(db: SqlSession, user_id: str, entity_id: str) -> bool:
    """True when this user has already saved this entity (initial heart state)."""
    return (
        db.query(UserFavorite.id)
        .filter(UserFavorite.user_id == user_id, UserFavorite.entity_id == entity_id)
        .first()
        is not None
    )


def favorite_count_for_user(db: SqlSession, user_id: str) -> int:
    cnt = db.query(func.count(UserFavorite.id)).filter(UserFavorite.user_id == user_id).scalar()
    return int(cnt or 0)


# --- Follow-venue (Phase A3) -------------------------------------------------
# "Following a venue" is a thin alias over favoriting a venue Entity. A venue is
# a commercial or place Entity (the kinds that host events); we deliberately do
# NOT treat an event Entity as a followable venue. Reuses UserFavorite so the
# weekend digest can surface events at the user's saved venues without a second
# storage concept.

_VENUE_ENTITY_TYPES = (ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE)


def entity_is_followable_venue(entity_type: str) -> bool:
    """True for entity types that can host events (commercial / place)."""
    return entity_type in _VENUE_ENTITY_TYPES


def follow_venue(db: SqlSession, user_id: str, entity_id: str) -> Literal["added", "exists"]:
    """Idempotently follow a venue. Returns 'added' or 'exists'.

    Unlike :func:`toggle_favorite`, following is intentionally idempotent so a
    repeat "follow" never silently un-follows. Does not commit; caller commits.
    """
    existing = (
        db.query(UserFavorite)
        .filter(UserFavorite.user_id == user_id, UserFavorite.entity_id == entity_id)
        .first()
    )
    if existing is not None:
        return "exists"
    db.add(UserFavorite(user_id=user_id, entity_id=entity_id))
    db.flush()
    return "added"


def unfollow_venue(db: SqlSession, user_id: str, entity_id: str) -> Literal["removed", "absent"]:
    """Idempotently unfollow a venue. Returns 'removed' or 'absent'."""
    existing = (
        db.query(UserFavorite)
        .filter(UserFavorite.user_id == user_id, UserFavorite.entity_id == entity_id)
        .first()
    )
    if existing is None:
        return "absent"
    db.delete(existing)
    db.flush()
    return "removed"


def followed_venue_entity_ids(db: SqlSession, user_id: str) -> list[str]:
    """Entity ids of the user's followed/saved venues (commercial + place)."""
    rows = (
        db.query(UserFavorite.entity_id)
        .join(Entity, Entity.id == UserFavorite.entity_id)
        .filter(
            UserFavorite.user_id == user_id,
            Entity.entity_type.in_(_VENUE_ENTITY_TYPES),
        )
        .order_by(UserFavorite.created_at.desc())
        .all()
    )
    return [r[0] for r in rows]
