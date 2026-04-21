"""Phase 6.4 — prior-entity pronoun fallback in ``unified_router`` (not entity_matcher)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.chat.unified_router import _enrich_entity_from_db, _prior_entity_fresh
from app.db.database import SessionLocal


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _intent_open() -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent="HOURS_LOOKUP",
        confidence=0.8,
        entity=None,
        raw_query="what time does it open",
        normalized_query="what time does it open",
    )


def test_prior_entity_fresh_boundary() -> None:
    sess = {"prior_entity": {"turn_number": 1, "name": "X", "id": "i", "type": "provider"}}
    assert _prior_entity_fresh(sess, 4) is not None
    assert _prior_entity_fresh(sess, 5) is None


def test_enrich_pronoun_uses_prior_when_fuzzy_misses(db: Session) -> None:
    ir = _intent_open()
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Altitude Trampoline Park — Lake Havasu City",
            "type": "provider",
            "turn_number": 1,
        }
    }
    out = _enrich_entity_from_db(
        "what time does it open?",
        ir,
        db,
        session=session,
        current_turn=2,
    )
    assert out.entity == "Altitude Trampoline Park — Lake Havasu City"


def test_enrich_explicit_entity_wins_over_prior(db: Session) -> None:
    ir = replace(
        _intent_open(),
        entity="Lake Havasu City BMX",
        raw_query="what time does bmx open",
        normalized_query="what time does bmx open",
    )
    session = {"prior_entity": {"id": "x", "name": "Altitude Trampoline Park — Lake Havasu City", "type": "provider", "turn_number": 1}}
    out = _enrich_entity_from_db(
        "what time does bmx open",
        ir,
        db,
        session=session,
        current_turn=2,
    )
    assert out.entity == "Lake Havasu City BMX"


def test_enrich_stale_prior_not_used(db: Session) -> None:
    ir = _intent_open()
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Altitude Trampoline Park — Lake Havasu City",
            "type": "provider",
            "turn_number": 1,
        }
    }
    out = _enrich_entity_from_db(
        "what time does it open?",
        ir,
        db,
        session=session,
        current_turn=5,
    )
    assert out.entity is None


def test_enrich_there_matches_prior(db: Session) -> None:
    ir = replace(_intent_open(), raw_query="what about there", normalized_query="what about there")
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Havasu Lanes",
            "type": "provider",
            "turn_number": 2,
        }
    }
    out = _enrich_entity_from_db(
        "what about there?",
        ir,
        db,
        session=session,
        current_turn=3,
    )
    assert out.entity == "Havasu Lanes"


def test_enrich_no_pronoun_no_prior_fallback(db: Session) -> None:
    ir = replace(
        _intent_open(),
        raw_query="what is good for dinner",
        normalized_query="what is good for dinner",
    )
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Havasu Lanes",
            "type": "provider",
            "turn_number": 1,
        }
    }
    out = _enrich_entity_from_db(
        "what is good for dinner",
        ir,
        db,
        session=session,
        current_turn=2,
    )
    assert out.entity is None
