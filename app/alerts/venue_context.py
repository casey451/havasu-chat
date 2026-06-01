"""UserFavorite venue context for alert emails (Phase 8a)."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Entity, UserFavorite


def indoor_favorites_for_user(db: Session, user_id: str, *, limit: int = 5) -> list[Entity]:
    return list(
        db.scalars(
            select(Entity)
            .join(UserFavorite, UserFavorite.entity_id == Entity.id)
            .where(UserFavorite.user_id == user_id)
            .where(Entity.heat_exposure.in_(("indoor", "shaded")))
            .order_by(UserFavorite.created_at.desc())
            .limit(limit)
        ).all()
    )


def land_favorites_for_user(db: Session, user_id: str, *, limit: int = 5) -> list[Entity]:
    return list(
        db.scalars(
            select(Entity)
            .join(UserFavorite, UserFavorite.entity_id == Entity.id)
            .where(UserFavorite.user_id == user_id)
            .where(
                or_(
                    Entity.heat_exposure.is_(None),
                    Entity.heat_exposure != "water_adjacent",
                )
            )
            .order_by(UserFavorite.created_at.desc())
            .limit(limit)
        ).all()
    )
