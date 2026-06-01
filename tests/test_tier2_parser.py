"""Tests for ``app.chat.tier2_parser`` — OpenAI client is always mocked.

Provider swap (2026-05-07): the parser calls ``call_anthropic_messages`` from
:mod:`app.core.llm_messages`, which is now an OpenAI wrapper (name retained for
call-site stability). Tests patch :mod:`app.core.llm_messages.OpenAI` and use
the OpenAI ``chat.completions`` response shape.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.core.llm_messages as llm_messages
from app.chat.tier2_parser import parse


def _msg(text: str) -> SimpleNamespace:
    """OpenAI chat.completions response shape with realistic usage counts."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[choice], usage=usage)


def _parse_with_mock(llm_text: str, query: str = "dummy"):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _msg(llm_text)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            f, tin, tout = parse(query)
    return f, tin, tout, fake_client


def _assert_high_conf(filters: object) -> None:
    assert filters is not None
    assert getattr(filters, "parser_confidence", 0) >= 0.7
    assert getattr(filters, "fallback_to_tier3", True) is False


def test_high_conf_what_should_i_do_saturday() -> None:
    payload = {
        "day_of_week": ["saturday"],
        "parser_confidence": 0.85,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "what should i do saturday")
    _assert_high_conf(filters)
    assert "saturday" in (filters.day_of_week or [])


def test_high_conf_pick_one_kids_weekend() -> None:
    payload = {
        "day_of_week": ["saturday", "sunday"],
        "category": "kids",
        "parser_confidence": 0.85,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(
        json.dumps(payload), "pick one thing to do with kids this weekend"
    )
    _assert_high_conf(filters)
    dow = filters.day_of_week or []
    tw = filters.time_window
    weekend_dow = "saturday" in dow and "sunday" in dow
    assert weekend_dow or tw == "this_weekend"
    kids_signal = (
        (filters.category and "kid" in filters.category.lower())
        or filters.age_min is not None
        or filters.age_max is not None
    )
    assert kids_signal


def test_high_conf_things_to_do_this_weekend() -> None:
    payload = {
        "time_window": "this_weekend",
        "parser_confidence": 0.8,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "things to do this weekend")
    _assert_high_conf(filters)
    dow = filters.day_of_week or []
    weekend_dow = "saturday" in dow and "sunday" in dow
    assert weekend_dow or filters.time_window == "this_weekend"


def test_high_conf_family_activities_this_month() -> None:
    payload = {
        "category": "family",
        "time_window": "this_month",
        "parser_confidence": 0.75,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "family activities this month")
    _assert_high_conf(filters)
    assert filters.time_window == "this_month"


def test_high_conf_your_favorite_event_coming_up() -> None:
    payload = {
        "time_window": "upcoming",
        "parser_confidence": 0.8,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "your favorite event coming up")
    _assert_high_conf(filters)
    assert filters.time_window == "upcoming"


def test_high_conf_events_tomorrow() -> None:
    """Verifies the parser passes its tuned ``max_tokens=300`` and
    ``temperature=0.3`` through to the OpenAI call. The Anthropic-era
    ``system[0].cache_control == ephemeral`` assertion is dropped — OpenAI's
    prompt caching is automatic and not surfaced per-call."""
    payload = {
        "time_window": "tomorrow",
        "parser_confidence": 0.85,
        "fallback_to_tier3": False,
    }
    filters, _, _, fake_client = _parse_with_mock(json.dumps(payload), "events tomorrow")
    _assert_high_conf(filters)
    assert filters.time_window == "tomorrow"
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 300
    assert kwargs["temperature"] == 0.3
    # Mock-seam invariant: only these four kwargs ever go to OpenAI.
    assert set(kwargs.keys()) == {"model", "max_tokens", "temperature", "messages"}


def test_high_conf_stuff_at_sara_park() -> None:
    payload = {
        "location": "Sara Park",
        "parser_confidence": 0.9,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "stuff happening at sara park")
    _assert_high_conf(filters)
    loc = (filters.location or "").lower()
    assert "sara park" in loc


def test_high_conf_best_bmx_program() -> None:
    payload = {
        "category": "bmx",
        "parser_confidence": 0.85,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "what is the best bmx program in town")
    _assert_high_conf(filters)
    cat = (filters.category or "").lower()
    ent = (filters.entity_name or "").lower()
    assert "bmx" in cat or "bmx" in ent


def test_high_conf_tell_me_about_bridge_city() -> None:
    payload = {
        "entity_name": "Bridge City",
        "parser_confidence": 0.9,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "tell me about bridge city")
    _assert_high_conf(filters)
    ent = (filters.entity_name or "").lower()
    assert "bridge city" in ent


def test_high_conf_six_year_old_burn_energy() -> None:
    payload = {
        "age_min": 6,
        "age_max": 6,
        "category": "active",
        "parser_confidence": 0.8,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(
        json.dumps(payload),
        "what is a good place for my 6-year-old to burn off some energy",
    )
    _assert_high_conf(filters)
    assert filters.age_min is not None
    assert 5 <= filters.age_min <= 7 or filters.age_max == 6


def test_fallback_tell_me_something_cool_about_town() -> None:
    payload = {
        "parser_confidence": 0.15,
        "fallback_to_tier3": True,
    }
    filters, _, _, _ = _parse_with_mock(
        json.dumps(payload), "tell me something cool about this town"
    )
    assert filters is not None
    assert filters.fallback_to_tier3 is True or filters.parser_confidence < 0.7


def test_fallback_whats_the_vibe_here() -> None:
    payload = {
        "parser_confidence": 0.35,
        "fallback_to_tier3": False,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "what's the vibe here")
    assert filters is not None
    assert filters.fallback_to_tier3 is True or filters.parser_confidence < 0.7


def test_fallback_anything_fun() -> None:
    payload = {
        "parser_confidence": 0.25,
        "fallback_to_tier3": True,
    }
    filters, _, _, _ = _parse_with_mock(json.dumps(payload), "anything fun")
    assert filters is not None
    assert filters.fallback_to_tier3 is True or filters.parser_confidence < 0.7


def test_sdk_error_returns_none() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("network")
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            f, tin, tout = parse("some query")
    assert f is None
    assert tin is None and tout is None


def test_invalid_json_returns_none() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _msg("not { valid json")
    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            f, tin, tout = parse("some query")
    assert f is None
    assert tin == 10 and tout == 5


def test_parse_prepends_date_context_to_system_prompt() -> None:
    """Wiring test for Backlog #3 (Slice 24): parse() prepends a 'Today's date is
    YYYY-MM-DD' preamble to the LLM system prompt so the parser can resolve year
    for ambiguous calendar queries.

    The preamble is constructed at runtime via app.core.timezone.now_lake_havasu()
    rather than baked into prompts/tier2_parser.txt, so the date never goes stale
    on disk. Without this wiring, a refactor could silently drop the prepend.

    Post-OpenAI swap: the system prompt lives in ``messages[0].content`` (OpenAI
    chat.completions shape), not in a top-level ``system`` kwarg (Anthropic shape).
    """
    import re

    payload = {
        "parser_confidence": 0.5,
        "fallback_to_tier3": True,
    }
    _, _, _, fake_client = _parse_with_mock(json.dumps(payload), "events on May 8")

    assert fake_client.chat.completions.create.called, "parse() should have called the LLM"
    messages = fake_client.chat.completions.create.call_args.kwargs.get("messages")
    assert isinstance(messages, list) and messages, "messages kwarg should be a non-empty list"
    system_msg = next((m for m in messages if m.get("role") == "system"), None)
    assert system_msg is not None, "messages should contain a system entry"
    system_text = system_msg.get("content", "")
    assert re.match(
        r"^Today's date is \d{4}-\d{2}-\d{2} \(Lake Havasu City",
        system_text,
    ), f"date preamble missing or wrong format; got: {system_text[:80]!r}"
