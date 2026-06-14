"""P2-2: weather-coping detector used by route() to force Tier-3.

The Tier-2-vs-Tier-3 split is decided by the LLM router, so coping phrasings landed
inconsistently — "indoor activities to beat the heat" got a Tier-2 swim-led events
listing while "what indoor activities are there" got the diversified Tier-3 answer.
route() now forces Tier-3 for weather-coping asks via _is_weather_coping. This pins
the detector (the route() override itself is exercised by the router integration
tests + live verification).
"""

from __future__ import annotations

from app.chat.unified_router import _is_weather_coping


def test_flags_weather_coping_queries() -> None:
    for q in (
        "indoor activities to beat the heat",
        "what should I do when it is too hot",
        "what can I do to stay cool",
        "indoor things to do when it is hot",
        "where can I cool off",
        "stuff to do to escape the heat",
    ):
        assert _is_weather_coping(q), q


def test_does_not_flag_ordinary_queries() -> None:
    for q in (
        "what should I do this weekend",
        "things to do tonight",
        "best mexican restaurant",
        "where can I rent a kayak",
        "cheap hotels near the lake",
    ):
        assert not _is_weather_coping(q), q
