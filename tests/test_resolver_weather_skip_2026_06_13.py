"""P1-2 / P2-2 root cause: weather-coping questions must not resolve to an events
intent (they wear a generic event word like "what should i do" / "to do").

Before this, "what should I do when it's too hot" matched _EVENT_WORDS and was
answered with a swim-heavy events list (Aquatic Center over-reliance). It now skips
the events branch and falls through (to Tier 3 for a real "beat the heat" answer),
while genuine "...this weekend / tonight" event browses still resolve to events.
"""

from __future__ import annotations

from app.chat.intents.resolver import resolve


def _is_events(query: str) -> bool:
    r = resolve(query)
    return r is not None and r.intent_key.startswith("events")


def test_weather_coping_queries_do_not_resolve_to_events() -> None:
    for q in (
        "what should I do when it is too hot",
        "what should we do when it's too hot",
        "things to do to beat the heat",
        "what's there to do to escape the heat",
    ):
        assert not _is_events(q), q


def test_genuine_event_browses_still_resolve_to_events() -> None:
    for q in (
        "what should I do this weekend",
        "what should we do tonight",
        "what's happening this week",
        "anything fun this weekend",
        "things to do this weekend",
    ):
        assert _is_events(q), q
