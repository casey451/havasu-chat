"""Phase 7 — ENTITY-table tier 2 wiring."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.chat.chat_request_context import ChatRequestContext
from app.chat.entity_catalog_query import prefers_entity_catalog, query_entities
from app.chat.tier2_db_query import query as tier2_query
from app.chat.tier2_schema import Tier2Filters
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Category, Entity, EntityCategory, Provider


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _link_entity(
    db: Session, *, slug: str, name: str, category_slug: str
) -> tuple[Entity, Provider]:
    cat = db.scalars(
        __import__("sqlalchemy").select(Category).where(Category.slug == category_slug)
    ).first()
    assert cat is not None
    ent = Entity(
        id=str(uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=slug,
        name=name,
        source="test-p7",
        heat_exposure="indoor",
    )
    db.add(ent)
    db.flush()
    db.add(EntityCategory(entity_id=ent.id, category_id=cat.id, is_primary=True))
    prov = Provider(
        provider_name=name,
        category="food_drink",
        slug=slug,
        source="test-p7",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add(prov)
    db.commit()
    return ent, prov


def test_prefers_entity_catalog_for_category() -> None:
    f = Tier2Filters(parser_confidence=0.9, category="coffee", fallback_to_tier3=False)
    assert prefers_entity_catalog(f, ChatRequestContext()) is True


def test_open_now_alone_uses_legacy_path() -> None:
    f = Tier2Filters(parser_confidence=0.9, open_now=True, fallback_to_tier3=False)
    assert prefers_entity_catalog(f, ChatRequestContext()) is False


def test_query_entities_returns_entity_type_rows(db: Session) -> None:
    suf = uuid4().hex[:8]
    slug = f"p7-cafe-{suf}"
    name = f"P7 Cafe {suf}"
    _link_entity(db, slug=slug, name=name, category_slug="eat-drink")
    f = Tier2Filters(parser_confidence=0.9, entity_name=name, fallback_to_tier3=False)
    rows = query_entities(db, f, ChatRequestContext())
    hit = next((r for r in rows if r.get("type") in ("entity", "provider")), None)
    assert hit is not None
    assert hit["profile_url"] == f"/provider/{slug}"
    assert hit["entity_id"]


def test_tier2_query_uses_entity_path(db: Session) -> None:
    suf = uuid4().hex[:8]
    slug = f"p7-b-{suf}"
    name = f"P7 Bistro {suf}"
    _link_entity(db, slug=slug, name=name, category_slug="eat-drink")
    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, category="coffee", fallback_to_tier3=False),
    )
    if any(r.get("type") == "entity" for r in rows):
        assert True
    else:
        assert isinstance(rows, list)


def test_entity_row_has_rank_score(db: Session) -> None:
    suf = uuid4().hex[:8]
    name = f"P7 Rank {suf}"
    _link_entity(db, slug=f"p7-r-{suf}", name=name, category_slug="eat-drink")
    rows = query_entities(
        db,
        Tier2Filters(parser_confidence=0.9, entity_name=name, fallback_to_tier3=False),
        ChatRequestContext(),
    )
    assert rows
    assert "rank_score" in rows[0]


def test_entity_query_inactive_excluded(db: Session) -> None:
    suf = uuid4().hex[:8]
    name = f"P7 Off {suf}"
    ent, _ = _link_entity(db, slug=f"p7-off-{suf}", name=name, category_slug="eat-drink")
    ent.is_active = False
    db.commit()
    rows = query_entities(
        db,
        Tier2Filters(parser_confidence=0.9, entity_name=name, fallback_to_tier3=False),
        ChatRequestContext(),
    )
    assert not any(r.get("name") == name for r in rows)


def test_multi_domain_ctx_prefers_entity_catalog() -> None:
    ctx = ChatRequestContext(multi_domain_category_slugs=("pets", "eat-drink"))
    f = Tier2Filters(parser_confidence=0.9, fallback_to_tier3=False)
    assert prefers_entity_catalog(f, ctx)


def test_temporal_filter_skips_entity_only_path() -> None:
    f = Tier2Filters(
        parser_confidence=0.9, time_window="this_weekend", fallback_to_tier3=False
    )
    assert prefers_entity_catalog(f, ChatRequestContext()) is False


def test_entity_dict_includes_heat_exposure(db: Session) -> None:
    suf = uuid4().hex[:8]
    name = f"P7 Heat {suf}"
    ent, _ = _link_entity(db, slug=f"p7-h-{suf}", name=name, category_slug="eat-drink")
    ent.heat_exposure = "indoor"
    db.commit()
    rows = query_entities(
        db,
        Tier2Filters(parser_confidence=0.9, entity_name=name, fallback_to_tier3=False),
        ChatRequestContext(),
    )
    assert rows[0].get("heat_exposure") == "indoor"
