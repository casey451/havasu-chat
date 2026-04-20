"""Tests for ``app.chat.tier2_parser`` — Anthropic client is always mocked."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.chat.tier2_parser import parse


def _msg(text: str) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[block], usage=usage)


def _parse_with_mock(llm_text: str, query: str = "dummy"):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg(llm_text)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
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
    payload = {
        "time_window": "tomorrow",
        "parser_confidence": 0.85,
        "fallback_to_tier3": False,
    }
    filters, _, _, fake_client = _parse_with_mock(json.dumps(payload), "events tomorrow")
    _assert_high_conf(filters)
    assert filters.time_window == "tomorrow"
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 300
    assert kwargs["temperature"] == 0.3
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


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
    filters, _, _, _ = _parse_with_mock(
        json.dumps(payload), "what is the best bmx program in town"
    )
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
    fake_client.messages.create.side_effect = RuntimeError("network")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            f, tin, tout = parse("some query")
    assert f is None
    assert tin is None and tout is None


def test_invalid_json_returns_none() -> None:
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg("not { valid json")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            f, tin, tout = parse("some query")
    assert f is None
    assert tin == 10 and tout == 5
