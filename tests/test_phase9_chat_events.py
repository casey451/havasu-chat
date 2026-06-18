"""Phase 9b — chat event-intent + tier-3 preamble."""

from __future__ import annotations

from unittest.mock import patch

from app.chat.chat_request_context import (
    EVENT_INTENT_TIER3_PREAMBLE,
    ChatRequestContext,
)
from app.chat.tier2_handler import _event_rows_for_intent, detect_event_intent
from app.events.queries import intent_window_for_when


def test_detect_tonight() -> None:
    assert detect_event_intent("what's happening tonight") == {
        "when": "tonight",
        "time_start": "17:00",
        "time_end": "23:59",
    }


def test_detect_this_weekend() -> None:
    assert detect_event_intent("events this weekend") == {"when": "this_weekend"}


def test_detect_non_event_none() -> None:
    assert detect_event_intent("best plumber near me") is None


def test_intent_window_tonight_is_today() -> None:
    from datetime import date

    today = date(2026, 6, 3)
    start, end = intent_window_for_when("tonight", today=today)
    assert start == today == end


def test_tier3_preamble_when_event_intent() -> None:
    ctx = ChatRequestContext(event_intent_when="tonight")
    assert EVENT_INTENT_TIER3_PREAMBLE in ctx.tier3_context_preambles()


def test_event_rows_for_intent_empty_ok() -> None:
    with patch("app.chat.tier2_handler.events_in_window", return_value=[]):
        rows = _event_rows_for_intent({"when": "today"})
    assert rows == []


# --- #4a: kids/family audience filter on the event agenda --------------------


def _fake_event(eid: str, title: str, tags: list[str]):
    from types import SimpleNamespace

    return SimpleNamespace(id=eid, title=title, tags=tags)


def test_event_rows_family_only_drops_adult_classes() -> None:
    from datetime import date

    d = date(2026, 6, 20)
    flat = [
        (_fake_event("1", "Kids Story Time", ["family", "kids"]), d),
        (_fake_event("2", "Aqua Aerobics", ["fitness"]), d),
        (_fake_event("3", "Arthritis Class", []), d),
    ]
    with patch("app.chat.tier2_handler.events_in_window", return_value=flat):
        with patch(
            "app.chat.tier2_handler._event_dict",
            side_effect=lambda e: {"type": "event", "name": e.title},
        ):
            rows = _event_rows_for_intent({"when": "this_weekend"}, family_only=True)
    names = [r["name"] for r in rows]
    assert "Kids Story Time" in names
    assert "Aqua Aerobics" not in names
    assert "Arthritis Class" not in names


def test_event_rows_without_family_only_keeps_all() -> None:
    from datetime import date

    d = date(2026, 6, 20)
    flat = [
        (_fake_event("1", "Kids Story Time", ["family"]), d),
        (_fake_event("2", "Aqua Aerobics", ["fitness"]), d),
    ]
    with patch("app.chat.tier2_handler.events_in_window", return_value=flat):
        with patch(
            "app.chat.tier2_handler._event_dict",
            side_effect=lambda e: {"type": "event", "name": e.title},
        ):
            rows = _event_rows_for_intent({"when": "this_weekend"}, family_only=False)
    names = [r["name"] for r in rows]
    assert "Kids Story Time" in names
    assert "Aqua Aerobics" in names
