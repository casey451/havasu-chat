"""Mock-based checks that ``parse()`` accepts well-formed date-related Tier2 JSON.

These do **not** assert that the real LLM, given the system prompt, produces this
JSON — only that the pipeline + ``Tier2Filters`` validation accept outputs of
this shape. Manual / browser verification of prompt behavior is Step 3.
"""

from __future__ import annotations

import json
import os
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
from app.chat.tier2_parser import parse
from app.chat.tier2_schema import Tier2Filters

# Reuses the pattern from test_tier2_parser.py; existing file not modified.


def _msg(text: str) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[block], usage=usage)


def _parse_with_mock(llm_text: str, query: str = "dummy") -> object:
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg(llm_text)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.object(anthropic, "Anthropic", return_value=fake_client):
            f, _tin, _tout = parse(query)
    return f


def _assert_resolves(
    query: str, payload: dict, want_date_exact=None, want_range: tuple | None = None
) -> Tier2Filters:
    """``filters`` is non-None, high confidence, and has no invalid temporal mix."""
    raw = {**payload, "parser_confidence": payload.get("parser_confidence", 0.85)}
    f = _parse_with_mock(json.dumps(raw), query)
    assert f is not None, "parse() must not fail validation for this payload"
    assert isinstance(f, Tier2Filters)
    assert f.parser_confidence >= 0.7
    assert f.fallback_to_tier3 is False
    if want_date_exact is not None:
        assert f.date_exact == want_date_exact
    if want_range is not None:
        a, b = want_range
        assert f.date_start == a
        assert f.date_end == b
    return f


def test_date_exact_single_temporal_group() -> None:
    f = _assert_resolves(
        "what is on 2026-05-08",
        {"date_exact": "2026-05-08", "fallback_to_tier3": False},
        want_date_exact=date(2026, 5, 8),
    )
    assert f.time_window is None
    assert f.month_name is None
    assert f.season is None
    assert f.date_start is None and f.date_end is None


def test_date_start_date_end_inclusive_range() -> None:
    f = _assert_resolves(
        "between june 1 and june 7",
        {
            "date_start": "2026-06-01",
            "date_end": "2026-06-07",
            "fallback_to_tier3": False,
        },
        want_range=(date(2026, 6, 1), date(2026, 6, 7)),
    )
    assert f.time_window is None
    assert f.date_exact is None
    assert f.month_name is None
    assert f.season is None


def test_month_name_no_time_window() -> None:
    f = _assert_resolves(
        "events in july",
        {"month_name": "july", "parser_confidence": 0.8, "fallback_to_tier3": False},
    )
    assert f.month_name == "july"
    assert f.time_window is None
    assert f.date_exact is None
    assert f.season is None
    assert f.date_start is None and f.date_end is None


def test_season_no_time_window() -> None:
    f = _assert_resolves(
        "summer fun",
        {"season": "summer", "parser_confidence": 0.8, "fallback_to_tier3": False},
    )
    assert f.season == "summer"
    assert f.time_window is None
    assert f.date_exact is None
    assert f.month_name is None
    assert f.date_start is None and f.date_end is None


def test_time_window_next_month_alone() -> None:
    f = _assert_resolves(
        "whats on next month",
        {"time_window": "next_month", "parser_confidence": 0.85, "fallback_to_tier3": False},
    )
    assert f.time_window == "next_month"
    assert f.date_exact is None
    assert f.date_start is None and f.date_end is None
    assert f.month_name is None
    assert f.season is None


def test_day_of_week_plus_time_window_allowed_with_model() -> None:
    f = _assert_resolves(
        "friday",
        {
            "day_of_week": ["friday"],
            "time_window": "upcoming",
            "parser_confidence": 0.8,
            "fallback_to_tier3": False,
        },
    )
    assert f.day_of_week == ["friday"]
    assert f.time_window == "upcoming"
    assert f.date_exact is None


def test_friday_may_8_2026_priority_is_date_exact_not_dow() -> None:
    f = _assert_resolves(
        "friday may 8 2026",
        {
            "date_exact": "2026-05-08",
            "parser_confidence": 0.9,
            "fallback_to_tier3": False,
        },
        want_date_exact=date(2026, 5, 8),
    )
    assert f.time_window is None
    assert f.month_name is None
    assert f.season is None
    assert f.date_start is None and f.date_end is None
    # Priority: do not set day_of_week when date_exact is set (per prompt contract)
    assert f.day_of_week is None


def test_next_week_in_allow_list() -> None:
    f = _assert_resolves(
        "x",
        {
            "time_window": "next_week",
            "parser_confidence": 0.8,
            "fallback_to_tier3": False,
        },
    )
    assert f.time_window == "next_week"
    assert f.date_exact is None


def test_temporal_group_conflict_rejected() -> None:
    """Pydantic rejects more than one of time_window, month, season, date_*, range."""
    bad = {
        "date_exact": "2026-05-08",
        "time_window": "upcoming",
        "parser_confidence": 0.9,
        "fallback_to_tier3": False,
    }
    f = _parse_with_mock(json.dumps(bad), "q")
    assert f is None
