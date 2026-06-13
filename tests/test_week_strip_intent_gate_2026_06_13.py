"""P1-2 regression: the week_strip must not fire for non-event questions.

is_week_strip_query keys only on filters + row counts, so a non-event query that
acquires a week-window filter and event-heavy rows (e.g. a "things to do" intent
defaulting to a 7-day window — "what should I do when it's too hot") wrongly
rendered a 7-day event strip. try_build_week_strip now gates on event intent in
the user's text first. These cases return None *before* the voice LLM call, so no
mock is needed.
"""

from __future__ import annotations

from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_week_strip import _query_has_event_intent, try_build_week_strip


def _event(day: str) -> dict:
    return {
        "type": "event",
        "date": day,
        "name": "Event",
        "start_time": "10:00",
        "location_name": "Aquatic Center",
    }


def _week_filters_and_events() -> tuple[Tier2Filters, list[dict]]:
    # A week-window filter + 5 event rows: enough that is_week_strip_query() alone
    # would say True. Only the intent gate should keep the strip from firing.
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    rows = [_event(f"2026-05-{d:02d}") for d in range(28, 33)]
    return f, rows


def test_non_event_query_does_not_fire_week_strip() -> None:
    f, rows = _week_filters_and_events()
    # The documented over-fire repro: a heat/things-to-do question, no event words.
    assert try_build_week_strip("what should I do when it is too hot", f, rows) is None


def test_event_intent_detection() -> None:
    # Fires for genuine event/what's-on questions...
    for q in (
        "what's on this week",
        "things to do this weekend",
        "any events tonight",
        "what's happening this week",
        "what is there to do",
    ):
        assert _query_has_event_intent(q) is True, q
    # ...and not for non-event questions.
    for q in (
        "what should I do when it is too hot",
        "where can I buy groceries",
        "is the water warm enough to swim",
        "best mexican restaurant",
    ):
        assert _query_has_event_intent(q) is False, q
