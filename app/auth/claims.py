"""Claim helpers — Phase 2A.3."""

from __future__ import annotations

from sqlalchemy.orm import Session as SqlSession

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE
from app.db.models import Claim, Entity


def entity_is_claimable(entity_type: str) -> bool:
    return entity_type in (ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE)


def find_existing_claim(db: SqlSession, user_id: str, entity_id: str) -> Claim | None:
    return db.query(Claim).filter(Claim.user_id == user_id, Claim.entity_id == entity_id).first()


def create_pending_claim(db: SqlSession, user_id: str, entity_id: str) -> Claim:
    """Insert a pending Claim after validating the Entity row.

    Raises ``sqlalchemy.exc.IntegrityError`` when a claim already exists for
    this (user_id, entity_id) pair.
    """
    ent = db.get(Entity, entity_id)
    if ent is None:
        raise ValueError("entity_not_found")
    if not entity_is_claimable(ent.entity_type):
        raise ValueError("not_claimable")
    row = Claim(user_id=user_id, entity_id=entity_id, status="pending")
    db.add(row)
    db.flush()
    return row


def get_entity_by_slug(db: SqlSession, slug: str) -> Entity | None:
    return db.query(Entity).filter(Entity.slug == slug).first()
