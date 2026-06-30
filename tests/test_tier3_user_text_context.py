"""Phase 6.4 — Tier 3 user_text includes User context and Now lines.

Migrated as part of §4.6: patches OpenAI seam (``app.core.llm_messages.OpenAI``)
and asserts on the user message at ``messages[1]`` (system is ``messages[0]``).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import app.core.llm_messages as llm_messages
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


@pytest.fixture(autouse=True)
def _clear_llm_response_cache() -> None:
    """These tests inspect ``create.call_args`` to assert on the LLM user message,
    so the call MUST happen — but ``answer_with_tier3`` short-circuits on a cache
    hit. The ``llm_response_cache`` table is shared across the whole pytest session
    and conftest's autouse row cleanup doesn't cover it, so an entry left by ANY
    other test (an exact OR an embedding-similarity match) makes ``create`` never
    fire and ``call_args`` is None (CI-only flake, ordering-dependent). Wipe it per
    test — same guard ``test_tier3_handler.py`` already uses."""
    from app.db.models import LlmResponseCache

    s = SessionLocal()
    try:
        s.query(LlmResponseCache).delete()
        s.commit()
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


def _resp(text: str, *, prompt_tokens: int = 1, completion_tokens: int = 1) -> SimpleNamespace:
    """OpenAI Chat Completions response shape."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


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
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp("ok")
    hints = {
        "visitor_status": "visiting",
        "has_kids": True,
        "age": 8,
        "location": "near the channel",
    }
    now = "Now: Tuesday, April 21, 2026, 3:00 PM"
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            answer_with_tier3("q", _intent(), db, onboarding_hints=hints, now_line=now)
    # OpenAI shape: messages[0]=system, messages[1]=user.
    content = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "User context:" in content
    assert "visiting" in content
    assert "with kids" in content
    assert "age 8" in content
    assert "near the channel" in content
    assert now in content
    assert "Local voice:" not in content
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
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp("ok")
    now = "Now: Monday, January 1, 2030, 12:00 PM"
    # Distinct query from the prior test ("q" → "qb") to avoid the shared
    # llm_response_cache table seeing a matching key from the same pytest
    # session and short-circuiting the LLM call we want to inspect here.
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            answer_with_tier3("qb", _intent(), db, onboarding_hints={}, now_line=now)
    content = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "User context:" not in content
    assert "Local voice:" not in content
    assert now in content
    assert "Context —" in content
