"""Issue 2 (2026-06-18): weekend/week event queries render a multi-day week_strip.

PR #392 fixed the wrong-day *label* (``resolve_target_date`` anchors a weekend
to its Friday). But a multi-day window still rendered a single ``day_agenda``
instead of the multi-day ``week_strip``. This covers the follow-up:

  * ``this_weekend`` is now a week-window shape (``_filters_scope_week_window``),
  * ``resolve_week_window`` returns the Fri–Sun weekend window,
  * ``build_week_strip`` renders exactly the window's days (Fri–Sun = 3 cells,
    not a padded 7), while a full week still renders 7,
  * ``_respond_event_intent`` emits a ``week_strip`` for multi-day windows
    (this_weekend / this_week) and keeps ``day_agenda`` for single days.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.chat import component_builders as cb
from app.chat import tier2_handler
from app.chat.tier2_schema import Tier2Filters


@pytest.fixture
def _thursday(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin "now" to Thursday 2026-06-18 so the weekend window is Fri 19 – Sun 21."""

    class _D:
        @staticmethod
        def date() -> date:
            return date(2026, 6, 18)  # Thursday

    monkeypatch.setattr(cb, "now_lake_havasu", lambda: _D())


def _event(day: str, *, name: str = "Event", start_time: str = "10:00") -> dict:
    return {
        "type": "event",
        "date": day,
        "name": name,
        "start_time": start_time,
        "location_name": "Aquatic Center",
        "tags": ["family"],
        "event_url": "https://example.com/e",
    }


# ─────────── filter / window plumbing ───────────


def test_this_weekend_is_a_week_window_shape() -> None:
    f = Tier2Filters(time_window="this_weekend", parser_confidence=1.0)
    assert cb._filters_scope_week_window(f) is True
    # And it must NOT be mistaken for a single day (day_agenda owns those).
    assert cb._filters_narrow_to_single_day(f) is False


def test_resolve_week_window_this_weekend_is_fri_to_sun(_thursday: None) -> None:
    f = Tier2Filters(time_window="this_weekend", parser_confidence=1.0)
    start, end = cb.resolve_week_window(f)
    assert start == date(2026, 6, 19)  # Friday
    assert end == date(2026, 6, 21)  # Sunday


def test_is_week_strip_query_matches_this_weekend(_thursday: None) -> None:
    f = Tier2Filters(time_window="this_weekend", parser_confidence=1.0)
    rows = [
        _event("2026-06-19", name="Fri1"),
        _event("2026-06-19", name="Fri2"),
        _event("2026-06-20", name="Sat1"),
        _event("2026-06-21", name="Sun1"),
    ]
    assert cb.is_week_strip_query(f, rows) is True


# ─────────── build_week_strip: variable length ───────────


def test_build_week_strip_weekend_renders_three_days(_thursday: None) -> None:
    f = Tier2Filters(time_window="this_weekend", parser_confidence=1.0)
    rows = [
        _event("2026-06-19", name="Fri"),
        _event("2026-06-20", name="Sat1"),
        _event("2026-06-20", name="Sat2", start_time="14:00"),
        _event("2026-06-21", name="Sun"),
    ]
    data = cb.build_week_strip(f, rows)

    assert len(data["days"]) == 3  # Fri–Sun, not a padded 7
    assert [d["date"] for d in data["days"]] == [
        "2026-06-19",
        "2026-06-20",
        "2026-06-21",
    ]
    assert [d["dow"] for d in data["days"]] == ["Fri", "Sat", "Sun"]
    assert [d["count"] for d in data["days"]] == [1, 2, 1]
    assert data["total_count"] == 4
    assert data["title"] == "Jun 19 – Jun 21"
    # Selected = first day with events (Friday); its agenda is that day only.
    assert data["selected_date"] == "2026-06-19"
    assert [a["title"] for a in data["agenda"]] == ["Fri"]


def test_build_week_strip_empty_weekend_uses_friday(_thursday: None) -> None:
    f = Tier2Filters(time_window="this_weekend", parser_confidence=1.0)
    data = cb.build_week_strip(f, [])
    assert len(data["days"]) == 3
    assert data["selected_date"] == "2026-06-19"
    assert data["agenda"] == []
    assert data["total_count"] == 0


def test_build_week_strip_this_week_still_seven_days(_thursday: None) -> None:
    """Regression: a full week is unchanged — seven day cells."""
    f = Tier2Filters(time_window="this_week", parser_confidence=1.0)
    data = cb.build_week_strip(f, [_event("2026-06-19") for _ in range(4)])
    assert len(data["days"]) == 7
    assert data["days"][0]["date"] == "2026-06-18"
    assert data["days"][6]["date"] == "2026-06-24"


# ─────────── _respond_event_intent routing ───────────


def test_respond_event_intent_weekend_renders_week_strip(_thursday: None) -> None:
    intent = {"when": "this_weekend"}
    rows = [
        _event("2026-06-19", name="Fri kids craft"),
        _event("2026-06-20", name="Sat splash pad"),
        _event("2026-06-21", name="Sun story time"),
    ]
    component_meta: dict = {}
    voice, *_ = tier2_handler._respond_event_intent(
        "things to do this weekend with kids",
        intent,
        rows,
        component_meta=component_meta,
    )
    assert component_meta["type"] == "week_strip"
    assert len(component_meta["data"]["days"]) == 3
    assert component_meta["data"]["days"][0]["dow"] == "Fri"
    assert voice and "?" not in voice


def test_respond_event_intent_empty_weekend_renders_empty_week_strip(
    _thursday: None,
) -> None:
    intent = {"when": "this_weekend"}
    component_meta: dict = {}
    tier2_handler._respond_event_intent(
        "anything happening this weekend",
        intent,
        [],
        component_meta=component_meta,
    )
    assert component_meta["type"] == "week_strip"
    assert len(component_meta["data"]["days"]) == 3
    assert component_meta["data"]["agenda"] == []


def test_respond_event_intent_today_still_day_agenda(_thursday: None) -> None:
    intent = {"when": "today"}
    rows = [
        _event("2026-06-18", name="Morning yoga"),
        _event("2026-06-18", name="Evening concert", start_time="19:00"),
    ]
    component_meta: dict = {}
    tier2_handler._respond_event_intent(
        "what's on today",
        intent,
        rows,
        component_meta=component_meta,
    )
    assert component_meta["type"] == "day_agenda"
    assert len(component_meta["data"]["events"]) == 2


def test_detect_event_intent_weekend_with_kids() -> None:
    """The reported query routes to the this_weekend event-intent path."""
    assert tier2_handler.detect_event_intent("things to do this weekend with kids") == {
        "when": "this_weekend"
    }
