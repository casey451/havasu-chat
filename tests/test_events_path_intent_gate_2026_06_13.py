"""P1-2 (part 2): the resolve()->run_query events path must also gate the week_strip
on event intent.

The documented over-fire ("what should I do when it's too hot" -> DATE_LOOKUP)
routes through runtime._build_events, not tier2_week_strip — so the gate added to
tier2_week_strip (PR #320) didn't catch it. _build_events now applies the same
guard and falls back to a voice-only list (no calendar widget) for non-event
questions. build_week_strip / fallback voice are pure, so no LLM mock is needed.
"""

from __future__ import annotations

from datetime import date

from app.chat.intents.queries import QueryResult
from app.chat.intents.runtime import _build_events

_TODAY = date(2026, 6, 15)


def _events(n: int = 5) -> list[dict]:
    return [
        {
            "type": "event",
            "date": f"2026-06-{15 + i:02d}",
            "name": f"E{i}",
            "start_time": "10:00",
            "location_name": "Aquatic Center",
        }
        for i in range(n)
    ]


def _result() -> QueryResult:
    # window="next_week" -> pure date math -> a 7-day (multi-day) window -> the
    # week_strip branch of _build_events.
    return QueryResult(
        "events_next_week", "events", _events(), "events",
        "Here's what's coming up:", window="next_week",
    )


def test_events_path_suppresses_strip_for_non_event_query() -> None:
    _voice, ctype, _data = _build_events(
        _result(), today=_TODAY, query="what should I do when it is too hot"
    )
    assert ctype == "none"  # no calendar widget for a non-event question


def test_events_path_keeps_strip_for_event_query() -> None:
    _voice, ctype, _data = _build_events(
        _result(), today=_TODAY, query="what is happening next week"
    )
    assert ctype == "week_strip"


def test_events_path_no_query_is_backward_compatible() -> None:
    # No threaded query -> unchanged legacy behavior (strip still builds).
    _voice, ctype, _data = _build_events(_result(), today=_TODAY)
    assert ctype == "week_strip"
