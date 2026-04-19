"""Tests for ``app.chat.unified_router`` (Phase 2.2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.chat.unified_router import ChatResponse, route
from app.db.database import SessionLocal
from app.db.models import ChatLog, Program
from app.schemas.program import ProgramCreate


def _insert_program(db: Session, provider_name: str) -> None:
    payload = ProgramCreate(
        title="Unified router test program title here",
        description="Twenty characters minimum description.",
        activity_category="sports",
        schedule_start_time="09:00",
        schedule_end_time="10:00",
        location_name="Lake Havasu City",
        provider_name=provider_name,
        tags=["unified_router_test"],
    )
    p = Program(
        title=payload.title,
        description=payload.description,
        activity_category=payload.activity_category,
        age_min=payload.age_min,
        age_max=payload.age_max,
        schedule_days=list(payload.schedule_days),
        schedule_start_time=payload.schedule_start_time,
        schedule_end_time=payload.schedule_end_time,
        location_name=payload.location_name,
        location_address=payload.location_address,
        cost=payload.cost,
        provider_name=payload.provider_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        contact_url=payload.contact_url,
        source=payload.source,
        is_active=payload.is_active,
        tags=list(payload.tags),
        embedding=payload.embedding,
    )
    db.add(p)
    db.commit()


def _latest_unified_log(db: Session) -> ChatLog | None:
    return db.scalars(select(ChatLog).order_by(ChatLog.created_at.desc()).limit(1)).first()


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_ask_placeholder_metadata(db: Session) -> None:
    r = route("What time does altitude open?", "sess-ask", db)
    assert isinstance(r, ChatResponse)
    assert r.mode == "ask"
    assert r.sub_intent == "TIME_LOOKUP"
    assert r.tier_used == "placeholder"
    assert "Ask mode:" in r.response
    assert "TIME_LOOKUP" in r.response
    assert 0 < r.latency_ms < 500
    row = _latest_unified_log(db)
    assert row is not None
    assert row.mode == "ask"
    assert row.latency_ms is not None and row.latency_ms > 0


def test_contribute_placeholder_contains_sub_intent(db: Session) -> None:
    r = route("I want to add a concert at the park on Friday at 8pm.", "sess-co", db)
    assert r.mode == "contribute"
    assert r.sub_intent == "NEW_EVENT"
    assert r.tier_used == "placeholder"
    assert "Contribute mode:" in r.response
    assert "NEW_EVENT" in r.response


def test_correct_placeholder(db: Session) -> None:
    r = route("That is wrong — the phone changed.", "sess-cr", db)
    assert r.mode == "correct"
    assert r.sub_intent == "CORRECTION"
    assert "Correct mode:" in r.response


def test_chat_greeting_one_of_variants(db: Session) -> None:
    r = route("Hi", "rot-test-a", db)
    assert r.mode == "chat"
    assert r.sub_intent == "GREETING"
    assert r.tier_used == "chat"
    assert r.response in (
        "Heya.",
        "Hey.",
        "Hey, good to see you.",
    )
    assert not r.response.rstrip().endswith("?")


def test_chat_greeting_same_session_stable(db: Session) -> None:
    r1 = route("Hello", "stable-greet-1", db)
    r2 = route("Hey", "stable-greet-1", db)
    assert r1.response == r2.response


def test_chat_out_of_scope_voice(db: Session) -> None:
    r = route("What is the weather this weekend?", "sess-oos", db)
    assert r.mode == "chat"
    assert r.sub_intent == "OUT_OF_SCOPE"
    assert "That's outside what I cover right now" in r.response
    assert "things-to-do" in r.response


def test_chat_small_talk_thanks(db: Session) -> None:
    r = route("Thanks", "sess-st", db)
    assert r.mode == "chat"
    assert r.sub_intent == "SMALL_TALK"
    assert r.response == "anytime."


def test_chat_small_talk_how_are_you(db: Session) -> None:
    r = route("How are you?", "sess-ha", db)
    assert r.response == "doing alright. what can I find for you?"


def test_classify_raises_still_logs_and_graceful(db: Session) -> None:
    before = db.scalars(select(ChatLog).order_by(ChatLog.created_at.desc()).limit(1)).first()
    with patch("app.chat.unified_router.classify", side_effect=RuntimeError("boom")):
        r = route("anything", "sess-err", db)
    assert r.response == "Something went sideways on my end — try that again in a sec."
    assert r.mode == "ask"
    row = _latest_unified_log(db)
    assert row is not None
    if before:
        assert row.id != before.id
    assert row.message == r.response


def test_entity_enrichment_when_classifier_has_no_entity(db: Session) -> None:
    canon = "Lake Havasu City BMX"
    _insert_program(db, canon)
    fake = IntentResult(
        mode="ask",
        sub_intent="HOURS_LOOKUP",
        confidence=0.7,
        entity=None,
        raw_query="hours question",
        normalized_query="hours question",
    )
    with patch("app.chat.unified_router.classify", return_value=fake):
        r = route("What are the hours for the bmx track in Lake Havasu?", "sess-enr", db)
    assert r.entity == canon
    row = _latest_unified_log(db)
    assert row is not None
    assert row.entity_matched == canon


def test_mode_handler_raises_graceful(db: Session) -> None:
    with patch("app.chat.unified_router._handle_ask", side_effect=ValueError("nope")):
        r = route("What time does altitude open?", "sess-h-err", db)
    assert "Something went sideways" in r.response
    row = _latest_unified_log(db)
    assert row is not None
    assert row.mode == "ask"
