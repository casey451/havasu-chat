"""Tests for ``app.chat.llm_router`` — Anthropic client is always mocked."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.chat.llm_router import RouterDecision, _load_router_system_prompt, route


def _msg(text: str) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[block], usage=usage)


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
    fake.messages.create.return_value = _msg(_valid_tier2_json())
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            d = route("what's on", "what's on")
    assert d is not None
    assert d.tier_recommendation == "2"
    assert d.tier2_filters is not None
    assert d.tier2_filters.time_window == "this_weekend"


def test_schema_accepts_tier3_with_null_tier2_filters() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg(_valid_tier3_json())
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            d = route("q", "q")
    assert d is not None
    assert d.tier_recommendation == "3"
    assert d.tier2_filters is None


def test_code_fenced_json_still_parses() -> None:
    body = f"```json\n{_valid_tier2_json()}\n```"
    fake = MagicMock()
    fake.messages.create.return_value = _msg(body)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            d = route("q", "q")
    assert d is not None
    assert d.tier_recommendation == "2"


def test_malformed_json_returns_none() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("not json {")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
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
    fake.messages.create.return_value = _msg(bad)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
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
    fake.messages.create.return_value = _msg(bad)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            assert route("q", "q") is None


def test_api_exception_returns_none() -> None:
    fake = MagicMock()
    fake.messages.create.side_effect = RuntimeError("api down")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            assert route("q", "q") is None


def test_missing_api_key_returns_none() -> None:
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
        with patch.object(anthropic, "Anthropic", lambda **k: MagicMock()):
            assert route("q", "q") is None


def test_load_router_prompt_contains_requirements() -> None:
    text = _load_router_system_prompt()
    assert "Section 4" in text
    assert "temporal" in text.lower() or "Temporal" in text
    assert "Example 1" in text
    assert "claude-haiku" not in text  # model is code-level, not required in prompt body


def test_messages_create_uses_haiku_model_and_zero_temp() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg(_valid_tier2_json())
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_MODEL": ""}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            route("q", "q")
    kw = fake.messages.create.call_args.kwargs
    assert "haiku" in str(kw.get("model", ""))
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
