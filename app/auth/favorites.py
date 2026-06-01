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


def favorite_count_for_user(db: SqlSession, user_id: str) -> int:
    cnt = db.query(func.count(UserFavorite.id)).filter(UserFavorite.user_id == user_id).scalar()
    return int(cnt or 0)
