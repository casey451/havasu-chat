"""Phase 6.4 — session memory helpers (hints, idle, turn, prior_entity)."""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.chat.hint_extractor import ExtractedHints
from app.core.session import (
    clear_session_state,
    get_session,
    record_entity,
    touch_session,
    update_hints_from_extraction,
)
from app.db.database import SessionLocal
from app.db.models import Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_fresh_session_defaults() -> None:
    clear_session_state("mem-fresh")
    s = get_session("mem-fresh")
    h = s["onboarding_hints"]
    assert h["visitor_status"] is None and h["has_kids"] is None
    assert h.get("age") is None and h.get("location") is None
    assert s["prior_entity"] is None
    assert s["last_activity_at"] is None
    assert s["turn_number"] == 0


def test_update_hints_from_extraction_sets_age() -> None:
    clear_session_state("mem-h1")
    update_hints_from_extraction("mem-h1", ExtractedHints(age=6, location=None))
    assert get_session("mem-h1")["onboarding_hints"]["age"] == 6
    assert get_session("mem-h1")["onboarding_hints"]["location"] is None


def test_update_hints_overwrites_age() -> None:
    clear_session_state("mem-h2")
    update_hints_from_extraction("mem-h2", ExtractedHints(age=6, location=None))
    update_hints_from_extraction("mem-h2", ExtractedHints(age="teenager", location=None))
    assert get_session("mem-h2")["onboarding_hints"]["age"] == "teenager"


def test_update_hints_none_noop() -> None:
    clear_session_state("mem-h3")
    update_hints_from_extraction("mem-h3", ExtractedHints(age=1, location=None))
    update_hints_from_extraction("mem-h3", None)
    assert get_session("mem-h3")["onboarding_hints"]["age"] == 1


def test_record_entity_writes_prior(db: Session) -> None:
    clear_session_state("mem-rec")
    db.add(
        Provider(
            provider_name="Session Mem Prov",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    record_entity("mem-rec", "Session Mem Prov", 7, db)
    pe = get_session("mem-rec")["prior_entity"]
    assert pe is not None
    assert pe["name"] == "Session Mem Prov"
    assert pe["turn_number"] == 7
    assert pe["type"] == "provider"
    assert pe["id"]


def test_touch_session_within_window_preserves_hints_and_flags() -> None:
    clear_session_state("mem-touch1")
    s = get_session("mem-touch1")
    s["onboarding_hints"]["age"] = 5
    s["awaiting_confirmation"] = True
    touch_session("mem-touch1")
    touch_session("mem-touch1")
    s2 = get_session("mem-touch1")
    assert s2["onboarding_hints"]["age"] == 5
    assert s2["awaiting_confirmation"] is True


def test_touch_session_after_idle_resets_hints_and_prior_not_flags() -> None:
    clear_session_state("mem-idle")
    s = get_session("mem-idle")
    s["onboarding_hints"]["age"] = 3
    s["prior_entity"] = {"id": "x", "name": "Y", "type": "provider", "turn_number": 1}
    s["awaiting_confirmation"] = True
    old = __import__("datetime").datetime.now(timezone.utc) - timedelta(minutes=31)
    s["last_activity_at"] = old
    touch_session("mem-idle")
    s2 = get_session("mem-idle")
    assert s2["onboarding_hints"]["age"] is None
    assert s2["prior_entity"] is None
    assert s2["awaiting_confirmation"] is True


def test_turn_number_increment_via_session() -> None:
    clear_session_state("mem-turn")
    s = get_session("mem-turn")
    s["turn_number"] = int(s.get("turn_number", 0)) + 1
    assert get_session("mem-turn")["turn_number"] == 1
    s["turn_number"] = int(s.get("turn_number", 0)) + 1
    assert get_session("mem-turn")["turn_number"] == 2
