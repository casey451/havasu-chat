"""Phase 4.3 — unified router Tier 2 attempt before Tier 3 (with chat_logs token split).

Migrated as part of §4.6: the two SDK-error tests now patch
``app.core.llm_messages.OpenAI`` (the canonical mock seam after the OpenAI swap).
The previous ``anthropic.Anthropic`` patches did not intercept the new code path,
which masked the formatter test's regression behind a coincidental real-call
failure on the placeholder API key.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.unified_router import ChatResponse, route
from app.db.database import SessionLocal
from app.db.models import ChatLog, Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _disable_llm_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_ROUTER", "false")


@pytest.fixture(autouse=True)
def _disable_hint_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.chat.unified_router.extract_hints", lambda *_a, **_kw: None)


def _latest_log(db: Session) -> ChatLog | None:
    return db.scalars(select(ChatLog).order_by(ChatLog.created_at.desc()).limit(1)).first()


def test_open_ended_tier2_happy_path_logs_split_tokens(db: Session) -> None:
    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=("Tier-2 stub answer.", 99, 40, 59),
    ):
        with patch(
            "app.chat.unified_router.answer_with_tier3",
            side_effect=AssertionError("Tier 3 must not run when Tier 2 succeeds"),
        ):
            r = route("What should we do Saturday?", "sess-t2-happy", db)
    assert isinstance(r, ChatResponse)
    assert r.mode == "ask"
    assert r.sub_intent == "OPEN_ENDED"
    assert r.tier_used == "2"
    assert r.response == "Tier-2 stub answer."
    assert r.llm_tokens_used == 99
    assert r.llm_input_tokens == 40
    assert r.llm_output_tokens == 59
    row = _latest_log(db)
    assert row is not None
    assert row.tier_used == "2"
    assert row.llm_tokens_used == 99
    assert row.llm_input_tokens == 40
    assert row.llm_output_tokens == 59


def test_open_ended_tier2_none_falls_back_to_tier3(db: Session) -> None:
    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=(None, None, None, None),
    ):
        with patch(
            "app.chat.unified_router.answer_with_tier3",
            return_value=("Tier-3 stub answer.", 32, 20, 12),
        ):
            r = route("What is fun to do this weekend?", "sess-t2-fb", db)
    assert r.tier_used == "3"
    assert r.response == "Tier-3 stub answer."
    assert r.llm_tokens_used == 32
    assert r.llm_input_tokens == 20
    assert r.llm_output_tokens == 12
    row = _latest_log(db)
    assert row is not None
    assert row.tier_used == "3"
    assert row.llm_tokens_used == 32
    assert row.llm_input_tokens == 20
    assert row.llm_output_tokens == 12


def test_tier1_unchanged_no_llm_tokens(db: Session) -> None:
    p = Provider(
        provider_name="Altitude Trampoline Park — Lake Havasu City",
        category="recreation",
        hours="10:00 AM – 8:00 PM daily",
        phone="928-555-0199",
        source="seed",
    )
    db.add(p)
    db.commit()
    with patch("app.chat.unified_router.try_tier2_with_usage") as t2:
        r = route("What time does altitude open?", "sess-t2-t1", db)
    t2.assert_not_called()
    assert r.tier_used == "1"
    assert r.llm_tokens_used is None
    assert r.llm_input_tokens is None
    assert r.llm_output_tokens is None
    row = _latest_log(db)
    assert row is not None
    assert row.tier_used == "1"
    assert row.llm_tokens_used is None


def test_tier1_none_invokes_tier2_then_tier3(db: Session) -> None:
    calls: list[str] = []

    def spy_tier2(q: str, **_kwargs: object) -> tuple[str | None, int | None, int | None, int | None]:
        # Accept **kwargs so the spy stays valid as the unified_router signature
        # evolves — current call sites pass ``component_meta=...`` and other
        # threaded context. We only care about counting invocations here.
        calls.append("t2")
        return ("Tier-2 via spy", 9, 5, 4)

    with patch("app.chat.unified_router.try_tier1", return_value=None):
        with patch("app.chat.unified_router.try_tier2_with_usage", side_effect=spy_tier2):
            with patch(
                "app.chat.unified_router.answer_with_tier3",
                side_effect=AssertionError("Tier 3 must not run when Tier 2 succeeds"),
            ):
                r = route("What is fun to do this weekend?", "sess-t1-none-t2-ok", db)
    assert calls == ["t2"]
    assert r.tier_used == "2"
    assert r.response == "Tier-2 via spy"


def test_tier1_none_tier2_none_silent_tier3(db: Session) -> None:
    with patch("app.chat.unified_router.try_tier1", return_value=None):
        with patch("app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)):
            with patch(
                "app.chat.unified_router.answer_with_tier3",
                return_value=("Tier-3 silent fallback.", 12, 7, 5),
            ):
                r = route("What is fun to do this weekend?", "sess-t1-t2-none", db)
    low = r.response.lower()
    assert "didn't understand" not in low
    assert "don't understand" not in low
    assert r.tier_used == "3"
    assert r.response == "Tier-3 silent fallback."


def test_tier2_parser_sdk_error_falls_through_to_tier3_route(db: Session) -> None:
    """Tier-2 parser-path failure should gracefully return the router placeholder."""
    sid = f"sess-t2-parser-boom-{uuid4().hex[:8]}"
    with patch("app.chat.unified_router.try_tier1", return_value=None):
        with patch(
            "app.chat.unified_router.try_tier2_with_usage",
            side_effect=RuntimeError("parser boom"),
        ):
            r = route("What is fun to do this weekend?", sid, db)
    assert r.tier_used == "placeholder"
    assert isinstance(r.response, str) and r.response.strip()


def test_tier2_formatter_sdk_error_falls_through_route(db: Session) -> None:
    """Tier-2 formatter-path failure should gracefully return the router placeholder."""
    sid = f"sess-t2-formatter-boom-{uuid4().hex[:8]}"
    with patch("app.chat.unified_router.try_tier1", return_value=None):
        with patch(
            "app.chat.unified_router.try_tier2_with_usage",
            side_effect=RuntimeError("formatter boom"),
        ):
            r = route(
                "Things to do tomorrow",
                sid,
                db,
            )
    assert r.tier_used == "placeholder"
    assert isinstance(r.response, str) and r.response.strip()


def test_gap_template_runs_after_tier2_no_rows(db: Session) -> None:
    with patch("app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)) as t2:
        with patch("app.chat.unified_router.answer_with_tier3") as t3:
            r = route("Where is Totally Fictional Venue XYZ?", "sess-t2-gap", db)
    t2.assert_called_once()
    t3.assert_not_called()
    assert r.tier_used == "gap_template"
    assert r.llm_tokens_used is None
    row = _latest_log(db)
    assert row is not None
    assert row.tier_used == "gap_template"
    assert row.llm_tokens_used is None
