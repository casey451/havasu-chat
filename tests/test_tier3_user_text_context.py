"""Phase 6.4 — Tier 3 user_text includes User context and Now lines."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.chat.tier3_handler import answer_with_tier3
from app.db.database import SessionLocal
from app.db.models import Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _intent() -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent="OPEN_ENDED",
        confidence=0.5,
        entity=None,
        raw_query="q",
        normalized_query="q",
    )


def _msg(text: str, *, usage: object | None) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], usage=usage)


def test_tier3_user_text_full_hints_and_fixed_now(db: Session) -> None:
    db.add(
        Provider(
            provider_name="Ctx T3",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    usage = SimpleNamespace(
        input_tokens=1,
        output_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg("ok", usage=usage)
    hints = {
        "visitor_status": "visiting",
        "has_kids": True,
        "age": 8,
        "location": "near the channel",
    }
    now = "Now: Tuesday, April 21, 2026, 3:00 PM"
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            answer_with_tier3("q", _intent(), db, onboarding_hints=hints, now_line=now)
    content = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "User context:" in content
    assert "visiting" in content
    assert "with kids" in content
    assert "age 8" in content
    assert "near the channel" in content
    assert now in content
    assert content.index("User context:") < content.index("Now:") < content.index("Context —")


def test_tier3_user_text_omits_user_context_when_empty_but_keeps_now(db: Session) -> None:
    db.add(
        Provider(
            provider_name="Ctx T3b",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    usage = SimpleNamespace(
        input_tokens=1,
        output_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg("ok", usage=usage)
    now = "Now: Monday, January 1, 2030, 12:00 PM"
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            answer_with_tier3("q", _intent(), db, onboarding_hints={}, now_line=now)
    content = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "User context:" not in content
    assert now in content
    assert "Context —" in content
