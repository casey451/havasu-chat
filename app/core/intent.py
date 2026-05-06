"""Thin deterministic helpers for Tier 1 routing (Slice 71).

Post–Backlog #36 Option A, production callers only need
``detect_out_of_scope_category`` (Tier 1 pre-screen in ``intent_classifier``)
and ``open_ended_search_message`` (retained per §7 disposition — currently no
``app/`` importer after the dormant ``search.py`` pipeline was removed).
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
            "rain",
            "raining",
            "is it going to rain",
            "going to rain",
        ),
    ),
    (
        "lodging",
        (
            "hotel",
            "motel",
            "airbnb",
            "where to stay",
            "where should i stay",
            "place to stay",
            "places to stay",
            "where can i stay",
            "accommodation",
            "accommodations",
            "lodging",
            "place to sleep",
            "where to sleep",
            "somewhere to stay",
        ),
    ),
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
    (
        "dining",
        (
            "restaurant",
            "where to eat",
            "best place to eat",
            "best places to eat",
            "dinner spot",
            "breakfast spot",
            "lunch spot",
            "brunch spot",
            "dining recommendation",
            "food recommendation",
            "good food in",
            "yelp",
            "breakfast",
        ),
    ),
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
    if re.search(r"\b(cheap|affordable)\b", m):
        return True
    if re.search(r"\b(rentals?)\b", m):
        return True
    if re.search(r"\bhire\b", m):
        return True
    if "book a " in m or "book me" in m or "book my " in m:
        return True
    if "venue for" in m:
        return True
    if "birthday party" in m or "wedding venue" in m or "party venue" in m:
        return True
    return False


def detect_out_of_scope_category(message: str) -> str | None:
    """Return the out-of-scope category name for ``message`` or ``None``.

    Returns one of ``"weather"``, ``"lodging"``, ``"transportation"``,
    ``"dining"``, or ``"commercial_services"`` when a category trigger matches
    and no event-signal token is present. The event-signal guard prevents false
    positives like "hotel grand opening event tonight" from being treated as
    lodging lookups.
    """
    m = message.lower()
    if "restaurant week" in m:
        return None
    if "night" in m and any(f"{word} night" in m for word in _NIGHT_ACTIVITY_WORDS):
        return None
    if _commercial_services_query(m):
        return "commercial_services"
    if any(word in m for word in _EVENT_INDICATOR_WORDS):
        return None
    for category, triggers in _OUT_OF_SCOPE_TRIGGERS:
        if any(t in m for t in triggers):
            return category
    return None


def open_ended_search_message(message: str) -> bool:
    m = message.lower().strip()
    return m in (
        "what's good?",
        "whats good?",
        "what's good",
        "whats good",
        "surprise me",
        "anything fun?",
        "anything fun",
    )
