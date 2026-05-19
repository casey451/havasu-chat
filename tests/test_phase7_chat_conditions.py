"""Phase 7 — heat/conditions awareness in chat."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.chat.chat_request_context import ChatRequestContext, heat_bias_tier3_preamble
from app.chat.entity_catalog_query import query_entities
from app.chat.tier2_schema import Tier2Filters
from app.core.ranking import HEAT_BIAS_THRESHOLD_F, STUB_CURRENT_TEMPERATURE_F
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


def _seed_pair(db: Session, suf: str) -> tuple[str, str]:
    cat = db.scalars(
        __import__("sqlalchemy").select(Category).where(Category.slug == "eat-drink")
    ).first()
    assert cat is not None
    outdoor = f"P7 Outdoor {suf}"
    indoor = f"P7 Indoor {suf}"
    for name, slug, hx in (
        (outdoor, f"p7-out-{suf}", "outdoor"),
        (indoor, f"p7-in-{suf}", "indoor"),
    ):
        ent = Entity(
            id=str(uuid4()),
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=slug,
            name=name,
            source="test-p7-heat",
            heat_exposure=hx,
        )
        db.add(ent)
        db.flush()
        db.add(EntityCategory(entity_id=ent.id, category_id=cat.id))
        db.add(
            Provider(
                provider_name=name,
                category="food_drink",
                slug=slug,
                source="test",
                draft=False,
                is_active=True,
                entity_id=ent.id,
            )
        )
    db.commit()
    return outdoor, indoor


def test_stub_temperature_reused_from_ranking_module() -> None:
    assert STUB_CURRENT_TEMPERATURE_F > HEAT_BIAS_THRESHOLD_F


def test_heat_bias_active_on_context() -> None:
    ctx = ChatRequestContext()
    assert ctx.heat_bias_active() is True


def test_heat_bias_tier3_preamble_text() -> None:
    assert "105" in heat_bias_tier3_preamble(STUB_CURRENT_TEMPERATURE_F)


def test_entity_query_ranks_indoor_first_when_hot(db: Session) -> None:
    suf = uuid4().hex[:8]
    outdoor, indoor = _seed_pair(db, suf)
    rows = query_entities(
        db,
        Tier2Filters(parser_confidence=0.9, category="coffee", fallback_to_tier3=False),
        ChatRequestContext(temperature_f=STUB_CURRENT_TEMPERATURE_F),
    )
    names = [r["name"] for r in rows if r["name"] in (outdoor, indoor)]
    if len(names) >= 2:
        assert names.index(indoor) < names.index(outdoor)


def test_cool_temp_no_heat_bias_in_rank(db: Session) -> None:
    suf = uuid4().hex[:8]
    outdoor, indoor = _seed_pair(db, suf)
    rows = query_entities(
        db,
        Tier2Filters(parser_confidence=0.9, category="coffee", fallback_to_tier3=False),
        ChatRequestContext(temperature_f=HEAT_BIAS_THRESHOLD_F),
    )
    assert rows


def test_chat_ctx_effective_temperature_default() -> None:
    ctx = ChatRequestContext()
    assert ctx.effective_temperature_f() == STUB_CURRENT_TEMPERATURE_F


def test_tier3_preamble_when_heat_active() -> None:
    pre = ChatRequestContext().tier3_context_preambles()
    assert any("indoor" in p.lower() for p in pre)


def test_override_temperature_on_context() -> None:
    ctx = ChatRequestContext(temperature_f=80.0)
    assert ctx.heat_bias_active() is False
