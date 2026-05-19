"""Phase 7 — boat-access mode in chat."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.chat_request_context import (
    BOAT_MODE_TIER3_PREAMBLE,
    ChatRequestContext,
    parse_chat_request_context,
)
from app.chat.entity_catalog_query import query_entities
from app.chat.tier2_schema import Tier2Filters
from app.chat.tier3_handler import answer_with_tier3
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


def test_parse_boat_from_query_param() -> None:
    ctx = parse_chat_request_context(query_params={"boat": "1"})
    assert ctx.boat_mode is True


def test_parse_boat_from_header() -> None:
    ctx = parse_chat_request_context(headers={"X-Boat-Mode": "1"})
    assert ctx.boat_mode is True


def test_parse_boat_from_preferred_mode() -> None:
    ctx = parse_chat_request_context(preferred_mode="boat")
    assert ctx.boat_mode is True


def test_boat_mode_filters_entities_with_boat_access(db: Session) -> None:
    cat = db.scalars(select(Category).where(Category.slug == "on-the-water")).first()
    assert cat is not None
    suf = uuid4().hex[:8]
    dock_name = f"P7 Dock {suf}"
    land_name = f"P7 Land {suf}"
    for name, slug, boat in (
        (dock_name, f"p7-dock-{suf}", {"dock": True}),
        (land_name, f"p7-land-{suf}", None),
    ):
        ent = Entity(
            id=str(uuid4()),
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=slug,
            name=name,
            source="test-p7-boat",
            boat_access=boat,
        )
        db.add(ent)
        db.flush()
        db.add(EntityCategory(entity_id=ent.id, category_id=cat.id))
        db.add(
            Provider(
                provider_name=name,
                category="lake_recreation",
                slug=slug,
                source="test-p7-boat",
                draft=False,
                is_active=True,
                entity_id=ent.id,
            )
        )
    db.commit()
    ctx = ChatRequestContext(boat_mode=True, multi_domain_category_slugs=("on-the-water",))
    rows = query_entities(
        db,
        Tier2Filters(parser_confidence=0.9, fallback_to_tier3=False),
        ctx,
    )
    names = {r["name"] for r in rows}
    assert dock_name in names
    assert land_name not in names


def test_tier3_preamble_includes_boat_mode() -> None:
    ctx = ChatRequestContext(boat_mode=True)
    assert BOAT_MODE_TIER3_PREAMBLE in ctx.tier3_context_preambles()


def test_boat_mode_off_returns_both_when_unfiltered(db: Session) -> None:
    cat = db.scalars(select(Category).where(Category.slug == "on-the-water")).first()
    assert cat is not None
    suf = uuid4().hex[:8]
    name = f"P7 Any {suf}"
    ent = Entity(
        id=str(uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=f"p7-any-{suf}",
        name=name,
        source="test",
    )
    db.add(ent)
    db.flush()
    db.add(EntityCategory(entity_id=ent.id, category_id=cat.id))
    db.add(
        Provider(
            provider_name=name,
            category="lake",
            slug=f"p7-any-{suf}",
            source="test",
            draft=False,
            is_active=True,
            entity_id=ent.id,
        )
    )
    db.commit()
    rows = query_entities(
        db,
        Tier2Filters(parser_confidence=0.9, entity_name=name, fallback_to_tier3=False),
        ChatRequestContext(boat_mode=False),
    )
    assert any(r["name"] == name for r in rows)


def test_boat_rank_boost_in_score(db: Session) -> None:
    from app.core.ranking import CardRankInput, compute_card_rank

    base = CardRankInput(distance_km=1.0, name="A", boat_access_populated=False)
    boat = CardRankInput(distance_km=1.0, name="B", boat_access_populated=True)
    assert compute_card_rank(boat, temperature_f=90.0) > compute_card_rank(base, temperature_f=90.0)


def test_answer_with_tier3_accepts_chat_ctx(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.chat.intent_classifier import IntentResult

    monkeypatch.setenv("OPENAI_API_KEY", "")
    ir = IntentResult(
        mode="ask",
        sub_intent="GENERAL_QUESTION",
        confidence=0.9,
        entity=None,
        raw_query="coffee",
        normalized_query="coffee",
    )
    text, *_ = answer_with_tier3("coffee", ir, db, chat_ctx=ChatRequestContext(boat_mode=True))
    assert text
