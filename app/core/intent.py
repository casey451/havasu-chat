"""Thin deterministic helpers for Tier 1 routing (Slice 71 + 71b).

Post–Backlog #36 Option A, the only production export is
``detect_out_of_scope_category`` — Tier 1 pre-screen in ``intent_classifier``
before the LLM call. Slice 71b removed ``open_ended_search_message`` after the
``search.py`` pipeline deletion left it without any caller.
"""

from __future__ import annotations

import re

# Out-of-scope category triggers. Each category is a tuple of lowercase
# substrings; a query matches the category if any substring appears.
_OUT_OF_SCOPE_TRIGGERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "weather",
        (
            "weather",
            "forecast",
            "temperature",
            "how hot",
            "how cold",
            "is it hot",
            "is it cold",
            "what to wear",
            "humidity",
            "rainfall",
            "is it going to rain",
            "going to rain",
        ),
    ),
    # Slice C5 (post Phase 8.11): the lodging bucket is intentionally removed,
    # mirroring the dining removal below. The catalog ships a populated
    # ``lodging-vacation-rentals`` category and the intent layer resolves a
    # working ``lodging_find`` for "hotel" / "where to stay" / "accommodation".
    # Routing those to the canned out-of-scope refusal made that whole category
    # unreachable from chat.
    (
        "transportation",
        (
            "directions",
            "how to get to",
            "how to get there",
            "how do i get there",
            "how far",
            "uber",
            "lyft",
            "taxi",
            "parking",
            "where do i park",
            "place to park",
            "rent a car",
            "car rental",
            "nearest airport",
            "closest airport",
            "drive to",
        ),
    ),
    # Slice F2 (post Phase 8.11): the dining bucket is intentionally removed. The
    # 2,266-row Google Places catalog now includes ~200 LHC restaurants, so phrases
    # like "restaurant", "where to eat", "best place to eat" route through Tier 2 /
    # Tier 3 against real catalog data instead of the chat-mode "outside what I cover"
    # reply. Yelp queries fall to Tier 3 too — the anti-hallucination rules in the
    # system prompt keep us from inventing details we don't have.
)

_EVENT_INDICATOR_WORDS: tuple[str, ...] = (
    "event",
    "events",
    "festival",
    "parade",
    "fireworks",
    "tournament",
    "concert",
    "gala",
    "fundraiser",
    "tour",
)

_NIGHT_ACTIVITY_WORDS: tuple[str, ...] = (
    "bike",
    "trivia",
    "karaoke",
    "comedy",
    "music",
    "movie",
    "paint",
    "open mic",
)

_COMMERCIAL_EVENT_RESCUE_PHRASES: tuple[str, ...] = (
    "rental event",
    "booking event",
    "open house",
    "ribbon cutting",
    "tour event",
    "grand opening",
)


def _commercial_services_query(m: str) -> bool:
    """Rentals, bookings, and venue shopping — not the event calendar."""
    if any(p in m for p in _COMMERCIAL_EVENT_RESCUE_PHRASES):
        return False
    # "cheap"/"affordable" removed (P1-1): they routed "cheap eats" /
    # "affordable restaurants" to the out-of-scope refusal, contradicting the
    # dining-in-scope decision. A bare price adjective is not a commercial
    # rental/booking signal.
    if re.search(r"\b(rentals?)\b", m):
        return True
    if re.search(r"\bhire\b", m):
        return True
    # "book a …" / "venue for …" / party + wedding venue removed: "book a table",
    # "book a haircut", "venue for a party", "where can I have a birthday party"
    # are catalog provider/venue intents the directory lists — the same unblock
    # as lodging (C5). Routing them to the canned out-of-scope refusal was the
    # same trap; catalog search + anti-hallucination guards return an honest gap
    # when coverage is thin instead of refusing. The rare off-catalog "book a
    # flight" gets that honest gap too. (rentals/hire kept — left for a broader
    # commercial-bucket review.)
    return False


# Weather "rain" must match as a whole word. The bare substring wrongly fired on
# "training" / "drain cleaning" and pushed real service queries to the
# out-of-scope refusal. (P1-1)
_WEATHER_RAIN_RE = re.compile(r"\brain(?:ing|ed|s)?\b")


def detect_out_of_scope_category(message: str) -> str | None:
    """Return the out-of-scope category name for ``message`` or ``None``.

    Returns ``"weather"``, ``"transportation"``, or ``"commercial_services"``
    when a category trigger matches and no event-signal token is present. The
    event-signal guard prevents false positives like "weather station tour"
    from being treated as weather lookups.
    """
    try:
        from app.chat.entity_intent import suppress_out_of_scope_for_factual_lookup

        if suppress_out_of_scope_for_factual_lookup(message):
            return None
    except Exception:
        pass
    m = message.lower()
    if "restaurant week" in m:
        return None
    if "night" in m and any(f"{word} night" in m for word in _NIGHT_ACTIVITY_WORDS):
        return None
    if _commercial_services_query(m):
        return "commercial_services"
    if any(word in m for word in _EVENT_INDICATOR_WORDS):
        return None
    if _WEATHER_RAIN_RE.search(m):
        return "weather"
    for category, triggers in _OUT_OF_SCOPE_TRIGGERS:
        if any(t in m for t in triggers):
            return category
    return None
