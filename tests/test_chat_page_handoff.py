"""Chat → leaf-page hand-off: listing-shaped asks route to the category page.

Covers ``leaf_query.match_leaf_for_chat`` (the broadened matcher used by the
in-thread chat path) and ``unified_router._leaf_page_handoff`` (voice +
``page_link`` component contract).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.categories import leaf_pages, leaf_query
from app.chat.unified_router import _leaf_page_handoff
from app.db.database import Base
from app.db.models import Category, Entity, EntityCategory, Provider


@pytest.fixture
def mem_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_leaf(db: Session, *, dept_slug: str, leaf_slug: str, leaf_name: str, n: int) -> None:
    dept = Category(slug=dept_slug, name=dept_slug.title(), sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug=leaf_slug, name=leaf_name, sort_order=0, level=1, parent_id=dept.id)
    db.add(leaf)
    db.flush()
    for _ in range(n):
        ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}", name="X")
        db.add(ent)
        db.flush()
        db.add(
            Provider(
                provider_name="X",
                category="x",
                slug=f"p-{uuid4().hex[:8]}",
                is_active=True,
                draft=False,
                entity_id=ent.id,
            )
        )
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    db.commit()


def _seed_grooming(db: Session, *, n: int = leaf_pages.LEAF_PAGE_MIN_PROVIDERS) -> None:
    _seed_leaf(db, dept_slug="pets", leaf_slug="grooming", leaf_name="Grooming", n=n)


# --- match_leaf_for_chat ------------------------------------------------------


def test_need_shaped_queries_route_to_leaf(mem_db: Session) -> None:
    _seed_grooming(mem_db)
    for q in (
        "i need a dog groomer",
        "I need a dog groomer",
        "looking for a dog groomer",
        "i'm looking for a pet groomer",
        "find me a dog groomer",
        "are there any dog groomers",
        "dog groomers",
    ):
        leaf = leaf_query.match_leaf_for_chat(mem_db, q)
        assert leaf is not None and leaf.slug == "grooming", q


def test_factual_or_temporal_payload_stays_conversational(mem_db: Session) -> None:
    _seed_grooming(mem_db)
    for q in (
        "dog groomer phone number",
        "what time does the dog groomer open",
        "i need a dog groomer tonight",
        "dog groomer hours",
        "i need a dog groomer open now",
        "how much does a dog groomer cost",
    ):
        assert leaf_query.match_leaf_for_chat(mem_db, q) is None, q


def test_descriptive_queries_stay_conversational(mem_db: Session) -> None:
    _seed_grooming(mem_db)
    assert leaf_query.match_leaf_for_chat(mem_db, "best groomer for an anxious dog") is None
    assert leaf_query.match_leaf_for_chat(mem_db, "") is None
    assert leaf_query.match_leaf_for_chat(mem_db, None) is None


def test_below_gate_leaf_does_not_route(mem_db: Session) -> None:
    _seed_grooming(mem_db, n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS - 1)
    assert leaf_query.match_leaf_for_chat(mem_db, "i need a dog groomer") is None


# --- _leaf_page_handoff (voice + component contract) -------------------------


def test_handoff_populates_page_link_component(mem_db: Session) -> None:
    _seed_grooming(mem_db)
    component_meta: dict = {}
    voice = _leaf_page_handoff("i need a dog groomer", mem_db, component_meta)
    assert voice is not None and "page" in voice.lower()
    assert component_meta["type"] == "page_link"
    data = component_meta["data"]
    assert data["url"] == "/categories/pets/grooming"
    assert data["label"] == "Grooming"
    assert data["count"] >= leaf_pages.LEAF_PAGE_MIN_PROVIDERS


def test_handoff_returns_none_for_non_navigational_query(mem_db: Session) -> None:
    _seed_grooming(mem_db)
    component_meta: dict = {}
    assert _leaf_page_handoff("why is my dog itchy", mem_db, component_meta) is None
    assert component_meta == {}
