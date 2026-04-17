from __future__ import annotations

import re
from typing import Any

from app.core.slots import extract_activity_family, extract_audience, extract_date_range

# Intent labels returned by detect_intent(message, session)
HARD_RESET = "HARD_RESET"
SOFT_CANCEL = "SOFT_CANCEL"
GREETING = "GREETING"
LISTING_INTENT = "LISTING_INTENT"
ADD_EVENT = "ADD_EVENT"
SERVICE_REQUEST = "SERVICE_REQUEST"
DEAL_SEARCH = "DEAL_SEARCH"
REFINEMENT = "REFINEMENT"
SEARCH_EVENTS = "SEARCH_EVENTS"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
UNCLEAR = "UNCLEAR"

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

# Strong event-signal tokens. When any of these appear in a query we
# yield on OUT_OF_SCOPE classification so events-about-a-venue queries
# (e.g. "hotel grand opening event tonight") still reach search.
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

_HARD_RESET_PHRASES = (
    "start over",
    "start from scratch",
    "cancel everything",
    "wipe everything",
)

_SOFT_CANCEL_PHRASES = (
    "never mind",
    "nevermind",
    "forget it",
    "nvm",
    "actually never mind",
    "scratch that",
)

_LISTING_PHRASES = (
    "show me all",
    "show all",
    "show everything",
    "show me everything",
    "list all",
    "list everything",
    "all events",
    "all of them",
    "everything",
    "what do you have",
    "what've you got",
    "what do you got",
    "what events",
    "what's on",
    "whats on",
    "what is on",
    "what's happening",
    "whats happening",
    "what's going on",
    "whats going on",
    "in your system",
    "in the system",
)

_ADD_CREATION_MARKERS = (
    "i'm hosting",
    "im hosting",
    "we're hosting",
    "were hosting",
    "i am hosting",
    "i'm running",
    "im running",
    "we're organizing",
    "were organizing",
    "i'm teaching",
    "im teaching",
    "add an event",
    "add event",
    "post an event",
    "submit an event",
    "registering",
    "tickets at",
    "ticket link",
    "eventbrite",
    "rsvp at",
    "there's a ",
    "theres a ",
    "there is a ",
)

_SERVICE_MARKERS = (
    "plumber",
    "electrician",
    "hvac",
    "roof repair",
    "my water heater",
    "who does ",
    "i need a ",
    "is broken",
    "fix my ",
)

_DEAL_MARKERS = (
    "deal",
    "coupon",
    "specials",
    "happy hour",
    "discount",
    "promo code",
)

SINGLE_WORD_ACTIVITIES = frozenset(
    {
        "golf",
        "tennis",
        "yoga",
        "pickleball",
        "basketball",
        "bjj",
        "pilates",
        "hiking",
        "running",
        "swimming",
        "crossfit",
        "zumba",
        "barre",
        "cycling",
    }
)

GREETING_TOKENS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "hiya",
        "howdy",
        "morning",
        "evening",
        "good morning",
        "good afternoon",
        "good evening",
        "hi there",
        "hey there",
        "hello there",
    }
)

CONFIRMATION_PHRASES = ["yes", "yep", "correct", "looks good", "that's right", "thats right"]
REJECTION_PHRASES = ["no", "nope", "not quite", "incorrect", "wrong"]

SKIP_OPTIONAL_CONTACT_PHRASES = (
    "skip",
    "no thanks",
    "none",
    "n/a",
    "nothing",
    "not needed",
    "pass",
)


def _word_boundary(lowered: str, word: str) -> bool:
    return bool(re.search(rf"(^|[^a-z0-9]){re.escape(word)}([^a-z0-9]|$)", lowered))


def is_hard_reset(message: str) -> bool:
    msg = message.lower().strip()
    if any(p in msg for p in _HARD_RESET_PHRASES):
        return True
    if _word_boundary(msg, "reset"):
        return True
    return False


def is_soft_cancel(message: str) -> bool:
    msg = message.lower().strip()
    if any(p in msg for p in _SOFT_CANCEL_PHRASES):
        return True
    if _word_boundary(msg, "cancel") and "cancel everything" not in msg:
        # standalone cancel → soft unless phrased as total wipe
        return True
    return False


def is_cancel_or_restart(message: str) -> bool:
    """True for full reset (hard) or soft bail phrases."""
    return is_hard_reset(message) or is_soft_cancel(message)


def _has_time_or_date_reference(msg: str) -> bool:
    lowered = msg.lower()
    if extract_date_range(msg) is not None:
        return True
    if any(x in lowered for x in ("today", "tomorrow", "tonight", "this weekend", "next week")):
        return True
    if re.search(r"\b\d{1,2}\s*(:\d{2})?\s*(am|pm)\b", lowered):
        return True
    if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)\b", lowered):
        return True
    if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", lowered):
        return True
    if re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", lowered):
        return True
    if re.search(r"\b(at|@)\s*\d{1,2}\b", lowered):
        return True
    return False


def _add_creation_language(msg: str) -> bool:
    m = msg.lower()
    if any(marker in m for marker in _ADD_CREATION_MARKERS):
        return True
    if "http://" in m or "https://" in m:
        return True
    if re.search(r"\badd\b", m) and _has_time_or_date_reference(msg):
        return True
    return False


def _add_meta_intent_question(msg: str) -> bool:
    """How-to / permission questions about posting an event — ADD_EVENT without a date yet."""
    m = msg.lower().strip().rstrip("?!.")
    phrases = (
        "can i add an event",
        "can we add an event",
        "could i add an event",
        "how do i add an event",
        "how to add an event",
        "how can i add an event",
        "where do i add an event",
        "where can i add an event",
        "i want to add an event",
        "i'd like to add an event",
        "id like to add an event",
        "can i post an event",
        "how do i post an event",
        "could we add an event",
    )
    return any(p in m for p in phrases)


def _active_non_search_flow(session: dict[str, Any]) -> bool:
    return bool(
        session.get("partial_event")
        or session.get("awaiting_confirmation")
        or session.get("awaiting_optional_contact")
        or session.get("awaiting_missing_field")
        or session.get("awaiting_duplicate_confirmation")
        or session.get("awaiting_merge_details")
        or session.get("awaiting_review_offer")
    )


def _listing_hit(msg: str) -> bool:
    m = msg.lower()
    return any(p in m for p in _LISTING_PHRASES)


def _refinement_looks_like_filter(message: str) -> bool:
    stripped = message.lower().strip().rstrip("?").strip()
    words = stripped.split()
    if len(words) == 1 and words[0] in SINGLE_WORD_ACTIVITIES:
        return True
    if extract_date_range(message):
        return True
    if extract_activity_family(message):
        return True
    if extract_audience(message):
        return True
    if len(stripped) <= 24 and extract_activity_family(message) is None and len(words) == 1:
        return words[0] in ("sports", "arts", "kids", "family", "outdoors", "learning", "classes")
    return False


def detect_out_of_scope_category(message: str) -> str | None:
    """Return the out-of-scope category name for ``message`` or ``None``.

    Returns one of ``"weather"``, ``"lodging"``, ``"transportation"``,
    ``"dining"`` when a category trigger matches and no event-signal
    token is present. The event-signal guard prevents false positives
    like "hotel grand opening event tonight" from being treated as
    lodging lookups.
    """
    m = message.lower()
    if "restaurant week" in m:
        return None
    if any(word in m for word in _EVENT_INDICATOR_WORDS):
        return None
    if "night" in m and any(f"{word} night" in m for word in _NIGHT_ACTIVITY_WORDS):
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


def detect_intent(message: str, session: dict[str, Any] | None = None) -> str:
    session = session or {}
    msg = message.strip()
    lowered = msg.lower()

    if is_hard_reset(msg):
        return HARD_RESET
    if is_soft_cancel(msg):
        return SOFT_CANCEL

    if detect_out_of_scope_category(msg) is not None:
        return OUT_OF_SCOPE

    flow = session.get("flow") or {}
    awaiting = flow.get("awaiting")

    if is_greeting(msg) and not _listing_hit(msg) and not _active_non_search_flow(session):
        return GREETING

    if _listing_hit(msg):
        return LISTING_INTENT

    if any(s in lowered for s in _SERVICE_MARKERS):
        return SERVICE_REQUEST
    if any(s in lowered for s in _DEAL_MARKERS):
        return DEAL_SEARCH

    if _add_meta_intent_question(msg):
        return ADD_EVENT

    if awaiting == "narrow_followup" and _refinement_looks_like_filter(msg):
        return REFINEMENT

    stripped_q = lowered.rstrip("?").strip()
    words = stripped_q.split()
    if len(words) == 1 and words[0] in SINGLE_WORD_ACTIVITIES:
        return SEARCH_EVENTS

    if _add_creation_language(msg) and _has_time_or_date_reference(msg):
        return ADD_EVENT

    if _add_creation_language(msg) and not _has_time_or_date_reference(msg):
        return SEARCH_EVENTS

    if len(msg) < 3 and not _active_non_search_flow(session) and awaiting is None:
        return UNCLEAR

    return SEARCH_EVENTS


def is_confirmation(message: str) -> bool:
    msg = message.lower().strip()
    return any(phrase in msg for phrase in CONFIRMATION_PHRASES)


def is_rejection(message: str) -> bool:
    msg = message.lower().strip()
    return any(phrase in msg for phrase in REJECTION_PHRASES)


def is_skip_optional_contact(message: str) -> bool:
    msg = message.lower().strip()
    if is_rejection(message):
        return True
    return any(p in msg for p in SKIP_OPTIONAL_CONTACT_PHRASES)


def is_greeting(message: str) -> bool:
    m = message.lower().strip().rstrip("!?")
    if not m:
        return False
    if m in GREETING_TOKENS:
        return True
    parts = m.split()
    if len(parts) <= 3 and parts[0] in ("hi", "hello", "hey") and len(m) <= 32:
        return True
    return False


def escape_to_search(message: str) -> bool:
    """User abandons add flow for browsing."""
    m = message.lower()
    return any(
        x in m
        for x in (
            "just looking",
            "only looking",
            "was just looking",
            "what's on",
            "whats on",
            "show me events",
            "looking for what's on",
        )
    )
