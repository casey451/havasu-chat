"""C6: entity-catalog rows must be ordered by the boosted card score.

The old sort rebuilt a stripped ``CardRankInput`` (no verified / open-now /
mobile / liveness fields) so the boosts that produced the emitted ``rank_score``
never affected row order. This pins that the ordering reflects the score.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.chat.chat_request_context import ChatRequestContext
from app.chat.entity_catalog_query import _fetch_ranked_entities
from app.chat.tier2_schema import Tier2Filters
from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Category, Entity, EntityCategory, Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed(db: Session, cat_id: int, *, name: str, verified: bool) -> Entity:
    eid = str(uuid.uuid4())
    ent = Entity(
        id=eid,
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=f"ent-{uuid.uuid4().hex[:12]}",
        name=name,
        source="test-c6",
        is_active=True,
    )
    db.add(ent)
    db.add(EntityCategory(entity_id=eid, category_id=cat_id, is_primary=True))
    db.add(
        Provider(
            provider_name=name,
            slug=f"prov-{uuid.uuid4().hex[:10]}",
            category="food_drink",
            source="test-c6",
            draft=False,
            is_active=True,
            verified=verified,
            entity_id=eid,
        )
    )
    db.flush()
    return ent


def test_catalog_ranks_verified_above_unverified_peer(db: Session) -> None:
    token = f"zqx{uuid.uuid4().hex[:8]}"
    cat = db.query(Category).order_by(Category.id).first()
    assert cat is not None
    eids: list[str] = []
    try:
        # Name the verified peer "Zzz…" so the old name-tiebreak sort would rank
        # it LAST. Only the verified boost (carried in the score) lifts it first.
        verified = _seed(db, cat.id, name=f"Zzz {token} Spot", verified=True)
        plain = _seed(db, cat.id, name=f"Aaa {token} Spot", verified=False)
        eids = [verified.id, plain.id]
        db.commit()

        rows = _fetch_ranked_entities(
            db,
            Tier2Filters(entity_name=token, parser_confidence=0.9),
            ChatRequestContext(),
            category_slugs=None,
        )
        names = [r["name"] for r in rows]
        assert names == [f"Zzz {token} Spot", f"Aaa {token} Spot"], names
        assert rows[0]["rank_score"] >= rows[1]["rank_score"]
    finally:
        for eid in eids:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()
