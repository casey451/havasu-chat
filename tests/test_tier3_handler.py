"""Tests for ``app.chat.tier3_handler`` — OpenAI client is always mocked.

Provider swap (2026-05-07): ``call_anthropic_messages`` is now an OpenAI wrapper.
Tests patch ``app.core.llm_messages.OpenAI`` (the canonical mock seam — see
``app/core/llm_messages.py`` §"Mock-seam invariants") with an OpenAI-shaped fake.
The previous Anthropic-style ``messages.create`` mocks did not intercept the new
code path; this file was migrated as part of §4.6 (test suite update).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import app.core.llm_messages as llm_messages
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


@pytest.fixture(autouse=True)
def _clear_llm_response_cache() -> None:
    """Tier-3 cache key now scopes on normalized_query + sub_intent + entity
    (2026-06-11, CHAT_DEEP_DIVE §1D). Every test here reuses the same
    ``_intent()`` (normalized_query="hello there"), so the raw query no longer
    differentiates the key — without a per-test reset the first test's stored
    answer is served to the rest as an exact-key hit. conftest's autouse row
    cleanup does not cover ``llm_response_cache``."""
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
        raw_query="hello there",
        normalized_query="hello there",
    )


def _resp(text: str, *, prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    """OpenAI Chat Completions response shape: choices[0].message.content + usage.

    The tier3 handler reads ``result.text`` (extracted from
    ``choice.message.content``) and ``result.usage`` (built from
    ``usage.prompt_tokens`` / ``completion_tokens`` via
    :meth:`Usage.from_sdk_usage`). Cache fields are zeroed by design — the
    helper does not surface OpenAI's automatic prompt caching per call.
    """
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


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
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp(
        "Concise answer here.", prompt_tokens=15, completion_tokens=5
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            text, tokens, tin, tout = answer_with_tier3("What is fun?", _intent(), db)
    assert text == "Concise answer here."
    assert tokens == 20
    assert tin == 15 and tout == 5
    fake_client.chat.completions.create.assert_called_once()


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
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
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
    fake_client.chat.completions.create.side_effect = RuntimeError("network")
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
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
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp(
        "   ", prompt_tokens=1, completion_tokens=1
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            text, tokens, tin, tout = answer_with_tier3("q", _intent(), db)
    assert text == FALLBACK_MESSAGE
    assert tokens is None and tin is None and tout is None


def test_usage_sums_input_output_tokens(db: Session) -> None:
    """OpenAI swap: only ``prompt_tokens + completion_tokens`` count toward the
    total. Cache token fields are zeroed by ``Usage.from_sdk_usage`` (OpenAI's
    automatic prompt caching is a subset of ``prompt_tokens``, so surfacing it
    separately would double-count)."""
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
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp(
        "ok", prompt_tokens=350, completion_tokens=40
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            _text, tokens, tin, tout = answer_with_tier3("q", _intent(), db)
    assert tokens == 390
    assert tin == 350 and tout == 40


def test_compact_onboarding_user_context_line() -> None:
    assert compact_onboarding_user_context_line(None) is None
    assert compact_onboarding_user_context_line({}) is None
    line = compact_onboarding_user_context_line({"visitor_status": "visiting", "has_kids": True})
    assert line is not None
    assert line.startswith("User context:")
    assert "visiting" in line.lower()
    assert "kids" in line.lower()


def test_user_message_includes_onboarding_bias_before_catalog(db: Session) -> None:
    """OpenAI shape: messages[0] is the system prompt, messages[1] is the user
    text. The bias line / Now / Classifier / Context blocks all live inside
    the user content."""
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
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp(
        "ok", prompt_tokens=1, completion_tokens=1
    )
    hints = {"visitor_status": "local", "has_kids": False}
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            answer_with_tier3("q", _intent(), db, onboarding_hints=hints)
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1]["role"] == "user"
    user_content = kwargs["messages"][1]["content"]
    assert "User context:" in user_content
    assert "Now:" in user_content
    assert "Classifier:" in user_content
    cat_idx = user_content.index("Context —")
    bias_idx = user_content.index("User context:")
    now_idx = user_content.index("Now:")
    assert bias_idx < now_idx < cat_idx


def test_system_prompt_is_passed_to_openai(db: Session) -> None:
    """Replaces the prior Anthropic-only ``cache_control: ephemeral`` test —
    OpenAI's prompt caching is automatic and not surfaced per call. The
    behavior we still care about is that the system prompt reaches the
    model unaltered as ``messages[0].content``."""
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
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp(
        "reply", prompt_tokens=1, completion_tokens=1
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            answer_with_tier3(
                "user text here",
                _intent(),
                db,
                now_line="Now: Monday, January 1, 2030, 12:00 PM",
            )
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    # Mock-seam invariants from app/core/llm_messages.py: exactly these kwargs.
    assert set(kwargs.keys()) == {"model", "max_tokens", "temperature", "messages"}
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert isinstance(messages[0]["content"], str)
    assert len(messages[0]["content"]) > 0


def test_fallback_message_matches_handoff_spec() -> None:
    expected = (
        "Something went sideways on my end — try that again in a sec, "
        "or call the business directly if you're in a hurry."
    )
    assert FALLBACK_MESSAGE == expected


def test_fallback_message_matches_unified_router_alias() -> None:
    from app.chat import unified_router as ur

    assert FALLBACK_MESSAGE == ur._GRACEFUL


# ---------------------------------------------------------------------------
# Lane B-1 -- deferred cache store via BackgroundTasks
# ---------------------------------------------------------------------------


def _seed_provider(db: Session) -> None:
    db.add(
        Provider(
            provider_name="B1 Prov",
            category="misc",
            verified=True,
            draft=False,
            is_active=True,
        )
    )
    db.commit()


def test_answer_with_tier3_defers_cache_store_when_background_tasks_provided(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When BackgroundTasks is passed, cache_store does NOT run synchronously."""
    from fastapi import BackgroundTasks

    import app.chat.tier3_handler as tier3_handler

    _seed_provider(db)

    def fake_anthropic(**kw: object) -> SimpleNamespace:
        return SimpleNamespace(
            text="stubbed answer",
            raw=SimpleNamespace(usage=True),
            usage=SimpleNamespace(billable_input=10, output_tokens=5),
        )

    monkeypatch.setattr(tier3_handler, "call_anthropic_messages", fake_anthropic)
    monkeypatch.setattr(
        "app.chat.llm_cache._compute_query_embedding",
        lambda t: [0.01] * 1536,
    )

    bg = BackgroundTasks()
    pre_count = len(bg.tasks)

    with patch.dict(os.environ, {"OPENAI_API_KEY": "stub-key-not-used"}):
        text, total, in_t, out_t = answer_with_tier3(
            "b1 background test query",
            _intent(),
            db,
            chat_ctx=None,
            background_tasks=bg,
        )

    assert text == "stubbed answer"
    assert len(bg.tasks) == pre_count + 1, "cache_store should be deferred, not skipped"


def test_answer_with_tier3_falls_back_to_sync_store_when_no_background_tasks(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backward compat: callers that don't pass background_tasks still write synchronously."""
    from sqlalchemy import select

    from app.db.models import LlmResponseCache

    _seed_provider(db)
    monkeypatch.setattr(
        "app.chat.llm_cache._compute_query_embedding",
        lambda t: [0.01] * 1536,
    )

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp(
        "answer", prompt_tokens=1, completion_tokens=1
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "stub-key-not-used"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            out = answer_with_tier3(
                "b1 sync fallback test",
                _intent(),
                db,
                chat_ctx=None,
            )
    assert out[0] == "answer"
    rows = db.scalars(select(LlmResponseCache)).all()
    assert len(rows) >= 1, "sync path should have written a cache row"
