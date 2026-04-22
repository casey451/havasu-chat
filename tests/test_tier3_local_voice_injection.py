"""Phase 6.5-lite — Local voice block injected into Tier 3 user_text."""

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
    usage = SimpleNamespace(
        input_tokens=1,
        output_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg("ok", usage=usage)
    now = "Now: Tuesday, April 21, 2026, 3:00 PM"
    sample = [
        {
            "id": "inj",
            "keywords": ["paddleboard"],
            "category": "outdoors",
            "text": "Mornings are glassy on the channel — great for photos.",
        }
    ]
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            with patch("app.data.local_voice.LOCAL_VOICE", sample):
                answer_with_tier3(
                    "paddleboard rentals",
                    _intent(),
                    db,
                    onboarding_hints={},
                    now_line=now,
                )
    content = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
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
            with patch("app.data.local_voice.LOCAL_VOICE", []):
                answer_with_tier3("no keyword match", _intent(), db, onboarding_hints={}, now_line=now)
    content = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Local voice:" not in content
    assert now in content
