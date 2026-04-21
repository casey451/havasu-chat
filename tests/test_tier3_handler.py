"""Tests for ``app.chat.tier3_handler`` — Anthropic client is always mocked."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.chat.tier3_handler import (
    FALLBACK_MESSAGE,
    answer_with_tier3,
    compact_onboarding_user_context_line,
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


def _intent() -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent="OPEN_ENDED",
        confidence=0.5,
        entity=None,
        raw_query="hello there",
        normalized_query="hello there",
    )


def _msg(text: str, *, usage: object | None) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], usage=usage)


def test_success_returns_text_and_token_count(db: Session) -> None:
    db.add(
        Provider(
            provider_name="Ctx Prov",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=2,
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg("Concise answer here.", usage=usage)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            text, tokens, tin, tout = answer_with_tier3("What is fun?", _intent(), db)
    assert text == "Concise answer here."
    assert tokens == 20
    assert tin == 15 and tout == 5
    fake_client.messages.create.assert_called_once()


def test_missing_api_key_graceful(db: Session) -> None:
    db.add(
        Provider(
            provider_name="Only for context",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
        text, tokens, tin, tout = answer_with_tier3("q", _intent(), db)
    assert text == FALLBACK_MESSAGE
    assert tokens is None and tin is None and tout is None


def test_api_exception_graceful(db: Session) -> None:
    db.add(
        Provider(
            provider_name="P",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("network")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            text, tokens, tin, tout = answer_with_tier3("q", _intent(), db)
    assert text == FALLBACK_MESSAGE
    assert tokens is None and tin is None and tout is None


def test_empty_assistant_text_graceful(db: Session) -> None:
    db.add(
        Provider(
            provider_name="P2",
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
    fake_client.messages.create.return_value = _msg("   ", usage=usage)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            text, tokens, tin, tout = answer_with_tier3("q", _intent(), db)
    assert text == FALLBACK_MESSAGE
    assert tokens is None and tin is None and tout is None


def test_usage_sums_input_output_and_cache_fields(db: Session) -> None:
    db.add(
        Provider(
            provider_name="P3",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=40,
        cache_read_input_tokens=200,
        cache_creation_input_tokens=50,
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg("ok", usage=usage)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            _text, tokens, tin, tout = answer_with_tier3("q", _intent(), db)
    assert tokens == 390
    assert tin == 350 and tout == 40


def test_compact_onboarding_user_context_line() -> None:
    assert compact_onboarding_user_context_line(None) is None
    assert compact_onboarding_user_context_line({}) is None
    line = compact_onboarding_user_context_line(
        {"visitor_status": "visiting", "has_kids": True}
    )
    assert line is not None
    assert line.startswith("User context:")
    assert "visitor" in line.lower()
    assert "kids" in line.lower()


def test_user_message_includes_onboarding_bias_before_catalog(db: Session) -> None:
    db.add(
        Provider(
            provider_name="Bias Prov",
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
    hints = {"visitor_status": "local", "has_kids": False}
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            answer_with_tier3("q", _intent(), db, onboarding_hints=hints)
    kwargs = fake_client.messages.create.call_args.kwargs
    user_content = kwargs["messages"][0]["content"]
    assert "User context:" in user_content
    assert "Classifier:" in user_content
    cat_idx = user_content.index("Context —")
    bias_idx = user_content.index("User context:")
    assert bias_idx < cat_idx


def test_system_prompt_passed_with_ephemeral_cache_control(db: Session) -> None:
    db.add(
        Provider(
            provider_name="P4",
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
    fake_client.messages.create.return_value = _msg("reply", usage=usage)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            answer_with_tier3("user text here", _intent(), db)
    kwargs = fake_client.messages.create.call_args.kwargs
    system = kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["type"] == "text"
    assert "cache_control" in system[0]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert len(system[0]["text"]) > 0
