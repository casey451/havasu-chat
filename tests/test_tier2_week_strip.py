"""Tests for week_strip component builders and tier2_week_strip integration."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.chat.component_builders import (
    build_week_strip,
    fallback_week_strip_voice,
    is_week_strip_query,
    resolve_week_window,
)
from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_week_strip import try_build_week_strip


def _event(
    day: str,
    *,
    name: str = "Event",
    start_time: str = "10:00",
) -> dict:
    return {
        "type": "event",
        "date": day,
        "name": name,
        "start_time": start_time,
        "location_name": "Aquatic Center",
    }


def test_is_week_strip_query_matches_this_week() -> None:
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    rows = [_event(f"2026-05-{d:02d}") for d in range(28, 33)]
    assert is_week_strip_query(f, rows) is True


def test_is_week_strip_query_rejects_single_day() -> None:
    f = Tier2Filters(time_window="today", parser_confidence=0.9)
    rows = [_event("2026-05-28") for _ in range(4)]
    assert is_week_strip_query(f, rows) is False


def test_is_week_strip_query_rejects_too_few_events() -> None:
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    rows = [_event("2026-05-28"), _event("2026-05-29")]
    assert is_week_strip_query(f, rows) is False


def test_is_week_strip_query_rejects_provider_heavy() -> None:
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    rows = [_event(f"2026-05-{d:02d}") for d in range(28, 32)]
    rows += [{"type": "provider", "id": str(i), "name": f"P{i}"} for i in range(4)]
    assert is_week_strip_query(f, rows) is False


def test_resolve_week_window_this_week() -> None:
    today = date(2026, 5, 28)
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    with patch("app.chat.component_builders.now_lake_havasu") as mock_now:
        mock_now.return_value = MagicMock(date=lambda: today)
        start, end = resolve_week_window(f)
    assert start == today
    assert end == today + timedelta(days=6)


def test_resolve_week_window_next_week() -> None:
    wednesday = date(2026, 5, 28)
    f = Tier2Filters(time_window="next_week", parser_confidence=0.9)
    with patch("app.chat.component_builders.now_lake_havasu") as mock_now:
        mock_now.return_value = MagicMock(date=lambda: wednesday)
        start, end = resolve_week_window(f)
    assert start == date(2026, 6, 1)
    assert end == date(2026, 6, 7)


def test_build_week_strip_buckets_events_by_date() -> None:
    window_start = date(2026, 5, 26)
    f = Tier2Filters(
        date_start=window_start,
        date_end=window_start + timedelta(days=6),
        parser_confidence=0.9,
    )
    rows = [
        _event("2026-05-26", name="Mon"),
        _event("2026-05-27", name="Tue"),
        _event("2026-05-29", name="Thu"),
        _event("2026-06-01", name="Sun1"),
        _event("2026-06-01", name="Sun2", start_time="14:00"),
    ]
    with patch("app.chat.component_builders.now_lake_havasu") as mock_now:
        mock_now.return_value = MagicMock(date=lambda: date(2026, 5, 28))
        data = build_week_strip(f, rows)

    assert len(data["days"]) == 7
    counts = [d["count"] for d in data["days"]]
    assert counts == [1, 1, 0, 1, 0, 0, 2]
    assert data["selected_date"] == "2026-05-26"
    assert data["total_count"] == 5


def test_build_week_strip_agenda_matches_selected_day() -> None:
    window_start = date(2026, 5, 26)
    f = Tier2Filters(
        date_start=window_start,
        date_end=window_start + timedelta(days=6),
        parser_confidence=0.9,
    )
    rows = [
        _event("2026-05-26", name="Late", start_time="18:00"),
        _event("2026-05-26", name="Early", start_time="09:00"),
        _event("2026-05-27", name="Other day"),
    ]
    with patch("app.chat.component_builders.now_lake_havasu") as mock_now:
        mock_now.return_value = MagicMock(date=lambda: date(2026, 5, 28))
        data = build_week_strip(f, rows)

    assert data["selected_date"] == "2026-05-26"
    assert [a["title"] for a in data["agenda"]] == ["Early", "Late"]


def test_build_week_strip_empty_week_uses_window_start() -> None:
    window_start = date(2026, 5, 26)
    f = Tier2Filters(
        date_start=window_start,
        date_end=window_start + timedelta(days=6),
        parser_confidence=0.9,
    )
    with patch("app.chat.component_builders.now_lake_havasu") as mock_now:
        mock_now.return_value = MagicMock(date=lambda: date(2026, 5, 28))
        data = build_week_strip(f, [])

    assert data["selected_date"] == window_start.isoformat()
    assert data["agenda"] == []


def test_fallback_voice_busy_pattern() -> None:
    window = (date(2026, 5, 26), date(2026, 6, 1))
    rows = [
        _event("2026-05-26"),
        _event("2026-05-27"),
        _event("2026-05-28"),
        _event("2026-05-29"),
        _event("2026-05-30"),
        _event("2026-05-31"),
        _event("2026-06-01"),
        _event("2026-06-01", name="Second"),
    ]
    voice = fallback_week_strip_voice(rows, window)
    assert "?" not in voice
    assert voice.endswith(".")
    assert "busy" in voice
    assert "eight" in voice


def test_try_build_week_strip_returns_none_for_non_week_shape() -> None:
    f = Tier2Filters(time_window="today", parser_confidence=0.9)
    rows = [_event("2026-05-28") for _ in range(4)]
    assert try_build_week_strip("what's on today", f, rows) is None


def test_try_build_week_strip_llm_fallback_on_exception() -> None:
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    rows = [_event(f"2026-05-{d:02d}") for d in range(28, 33)]
    with patch(
        "app.chat.tier2_week_strip.call_anthropic_messages",
        side_effect=RuntimeError("llm down"),
    ):
        result = try_build_week_strip("what's on this week", f, rows)
    assert result is not None
    voice, data, v_in, v_out = result
    assert v_in == 0 and v_out == 0
    assert "?" not in voice
    assert len(data["days"]) == 7
