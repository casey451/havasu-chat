"""Tests for ``app.chat.llm_router`` — OpenAI client is always mocked.

Provider swap (2026-05-07): ``call_anthropic_messages`` is now an OpenAI
wrapper (name retained for call-site stability — see :mod:`app.core.llm_messages`).
These tests patch :mod:`app.core.llm_messages.OpenAI` directly because the
router calls ``call_anthropic_messages`` from that module.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.core.llm_messages as llm_messages
from app.chat.llm_router import RouterDecision, _load_router_system_prompt, route


def _resp(text: str) -> SimpleNamespace:
    """OpenAI chat.completions response shape with realistic usage counts."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    return SimpleNamespace(choices=[choice], usage=usage)


def _valid_tier2_json() -> str:
    return json.dumps(
        {
            "mode": "ask",
            "sub_intent": "OPEN_ENDED",
            "entity": None,
            "router_confidence": 0.85,
            "tier_recommendation": "2",
            "tier2_filters": {
                "time_window": "this_weekend",
                "open_now": False,
                "parser_confidence": 0.86,
                "fallback_to_tier3": False,
            },
        }
    )


def _valid_tier3_json() -> str:
    return json.dumps(
        {
            "mode": "ask",
            "sub_intent": "OPEN_ENDED",
            "entity": None,
            "router_confidence": 0.7,
            "tier_recommendation": "3",
            "tier2_filters": None,
        }
    )


def test_schema_accepts_valid_tier2_response() -> None:
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(_valid_tier2_json())
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            d = route("what's on", "what's on")
    assert d is not None
    assert d.tier_recommendation == "2"
    assert d.tier2_filters is not None
    assert d.tier2_filters.time_window == "this_weekend"


def test_schema_accepts_tier3_with_null_tier2_filters() -> None:
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(_valid_tier3_json())
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            d = route("q", "q")
    assert d is not None
    assert d.tier_recommendation == "3"
    assert d.tier2_filters is None


def test_code_fenced_json_still_parses() -> None:
    body = f"```json\n{_valid_tier2_json()}\n```"
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(body)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            d = route("q", "q")
    assert d is not None
    assert d.tier_recommendation == "2"


def test_malformed_json_returns_none() -> None:
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp("not json {")
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            assert route("q", "q") is None


def test_invalid_tier_recommendation_returns_none() -> None:
    bad = json.dumps(
        {
            "mode": "ask",
            "sub_intent": "OPEN_ENDED",
            "router_confidence": 0.8,
            "tier_recommendation": "1",
            "tier2_filters": None,
        }
    )
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(bad)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            assert route("q", "q") is None


def test_tier2_without_tier2_filters_returns_none() -> None:
    bad = json.dumps(
        {
            "mode": "ask",
            "sub_intent": "OPEN_ENDED",
            "router_confidence": 0.8,
            "tier_recommendation": "2",
            "tier2_filters": None,
        }
    )
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(bad)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            assert route("q", "q") is None


def test_api_exception_returns_none() -> None:
    fake = MagicMock()
    fake.chat.completions.create.side_effect = RuntimeError("api down")
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            assert route("q", "q") is None


def test_missing_api_key_returns_none() -> None:
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
        with patch.object(llm_messages, "OpenAI", lambda **k: MagicMock()):
            assert route("q", "q") is None


def test_load_router_prompt_contains_requirements() -> None:
    text = _load_router_system_prompt()
    assert "Section 4" in text
    assert "temporal" in text.lower() or "Temporal" in text
    assert "Example 1" in text
    assert "claude-haiku" not in text  # model is code-level, not required in prompt body


def test_messages_create_uses_default_model_and_zero_temp() -> None:
    """Router must call OpenAI with temperature=0 and the default ``gpt-4o-mini``
    model when ``OPENAI_MODEL`` is unset (post-Anthropic-swap)."""
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(_valid_tier2_json())
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k", "OPENAI_MODEL": ""}):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            route("q", "q")
    kw = fake.chat.completions.create.call_args.kwargs
    assert "gpt" in str(kw.get("model", "")).lower()
    assert kw.get("temperature") == 0.0
    assert kw.get("max_tokens") == 500


def test_router_decision_model_tier2_requires_filters() -> None:
    with pytest.raises(Exception):
        RouterDecision.model_validate(
            {
                "mode": "ask",
                "sub_intent": "OPEN_ENDED",
                "router_confidence": 0.8,
                "tier_recommendation": "2",
                "tier2_filters": None,
            }
        )
