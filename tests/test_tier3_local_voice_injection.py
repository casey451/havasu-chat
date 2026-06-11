"""Phase 6.5-lite — Local voice block injected into Tier 3 user_text.

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
    """Tier-3 cache key now scopes on normalized_query + sub_intent + entity
    (2026-06-11, CHAT_DEEP_DIVE §1D). Both tests here reuse the same
    ``_intent()`` (normalized_query="q"), so without a per-test reset the first
    test's stored answer is served to the second as an exact-key hit and the
    OpenAI mock is never called. conftest's autouse row cleanup does not cover
    ``llm_response_cache``."""
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


def test_tier3_injects_local_voice_between_now_and_context(db: Session) -> None:
    db.add(
        Provider(
            provider_name="Voice T3",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp("ok")
    now = "Now: Tuesday, April 21, 2026, 3:00 PM"
    sample = [
        {
            "id": "inj",
            "keywords": ["paddleboard"],
            "category": "outdoors",
            "text": "Mornings are glassy on the channel — great for photos.",
        }
    ]
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            with patch("app.data.local_voice.LOCAL_VOICE", sample):
                answer_with_tier3(
                    "paddleboard rentals",
                    _intent(),
                    db,
                    onboarding_hints={},
                    now_line=now,
                )
    # OpenAI shape: messages[0]=system, messages[1]=user.
    content = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "Local voice:" in content
    assert "- Mornings are glassy on the channel — great for photos." in content
    assert content.index("Now:") < content.index("Local voice:") < content.index("Context —")


def test_tier3_omits_empty_local_voice_payload(db: Session) -> None:
    db.add(
        Provider(
            provider_name="Voice T3b",
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
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            with patch("app.data.local_voice.LOCAL_VOICE", []):
                answer_with_tier3(
                    "no keyword match", _intent(), db, onboarding_hints={}, now_line=now
                )
    content = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "Local voice:" not in content
    assert now in content
