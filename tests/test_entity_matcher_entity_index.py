"""C-PR-4 (hunt 2026-06-10 §1 item 5): provider-less Entity names join the
Tier-1 fuzzy index.

"Havasu Stitchers" exists as a catalog Entity with no Provider row, so
"tell me about havasu stitchers" dead-ended at Tier-1. Entities owned by the
provider pipeline (any Provider row, draft included) stay excluded so the
provider-level draft/is_active gates keep applying.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.chat.entity_matcher as em
from app.db.database import Base
from app.db.models import Entity, Provider


@pytest.fixture
def mem_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    em.reset_entity_matcher()
    try:
        yield session
    finally:
        em.reset_entity_matcher()
        session.close()
        engine.dispose()


def _entity(db: Session, name: str, *, active: bool = True) -> Entity:
    e = Entity(
        entity_type="commercial",
        slug=f"e-{uuid4().hex[:8]}",
        name=name,
        is_active=active,
    )
    db.add(e)
    db.flush()
    return e


def test_provider_less_entity_is_matchable(mem_db: Session) -> None:
    _entity(mem_db, "Havasu Stitchers Community Outreach Sewing")
    mem_db.commit()
    hit = em.match_entity("tell me about havasu stitchers", mem_db)
    assert hit is not None
    assert hit[0] == "Havasu Stitchers Community Outreach Sewing"
    assert hit[1] > 75.0


def test_inactive_entity_not_indexed(mem_db: Session) -> None:
    _entity(mem_db, "Ghost Quilting Circle", active=False)
    mem_db.commit()
    assert em.match_entity("ghost quilting circle", mem_db) is None


def test_entity_with_provider_row_stays_provider_gated(mem_db: Session) -> None:
    e = _entity(mem_db, "Half Done Cafe")
    mem_db.add(
        Provider(
            provider_name="Half Done Cafe",
            slug=f"p-{uuid4().hex[:10]}",
            category="cafe",
            draft=True,
            is_active=True,
            entity_id=e.id,
        )
    )
    mem_db.commit()
    # Draft provider — the provider gate must keep this name out of the index
    # even though its entity row is active.
    assert em.match_entity("half done cafe", mem_db) is None


def test_event_shaped_entity_not_indexed(mem_db: Session) -> None:
    """Event-derived entity rows ("Alpha Open Meet") must not become Tier-1
    entities — they hijack "when is X at <provider>" queries via token-set 100
    + alphabetical tie-break (test_ask_mode regression, C-PR-4)."""
    e = Entity(
        entity_type="event",
        slug=f"e-{uuid4().hex[:8]}",
        name="Alpha Open Meet",
        is_active=True,
    )
    mem_db.add(e)
    mem_db.commit()
    assert em.match_entity("when is alpha open meet", mem_db) is None
