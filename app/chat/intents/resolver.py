"""L0-L2 intent resolver (Ask Hava intent catalog, Phase 1).

``resolve(query)`` maps a free-text question to a ``ResolvedIntent`` (intent
key + primitive slots + the matcher layer that caught it), or ``None`` when no
intent is confident -- ``None`` means "fall through to the existing Tier 2 /
Tier 3 path", which is the intended behavior, not a failure.

Design rules (master spec §0, §5):
* Cheapest layer that works. L1 keyword/regex first; L2 dictionary slot-fill.
* Conservative: when unsure, return ``None`` rather than guess. The existing
  router handles everything we don't claim.
* Slots are JSON-friendly primitives (strings / bools) so they can be logged
  and asserted in tests; the query layer re-derives routes from the dicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.chat.intents import dicts
from app.chat.normalizer import normalize
from app.core.slots import extract_date_range

# Layer labels (for telemetry / tests asserting min_layer).
L1 = "L1"
L2 = "L2"


@dataclass(frozen=True)
class ResolvedIntent:
    intent_key: str
    slots: dict[str, object] = field(default_factory=dict)
    layer: str = L1


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _word(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])")


def _has(text: str, term: str) -> bool:
    """Whole-word for short terms, substring for long phrases."""
    if len(term) <= 4 or " " not in term and len(term) <= 6:
        return bool(_word(term).search(text))
    return term in text


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_has(text, t) for t in terms)


# ---------------------------------------------------------------------------
# Slot extractors
# ---------------------------------------------------------------------------

_GAS_RE = re.compile(r"\b(gas|fuel|diesel|gasoline)\b")
_GAS_INTENT_RE = re.compile(
    r"\b(cheap|cheapest|low|lowest|best|price|prices|cost|where).{0,20}\b"
    r"(gas|fuel|diesel|gasoline)\b|\bgas\s+price"
)

_EVENT_WORDS = (
    "event",
    "events",
    "happening",
    "going on",
    "to do",
    "things to do",
    "live music",
    "concert",
    "festival",
    "what's on",
    "whats on",
)
_OPEN_NOW_RE = re.compile(r"\bopen\s+(now|right now|late)\b|\bopen\s*\?")

_FOOD_WORDS = (
    "eat",
    "restaurant",
    "restaurants",
    "food",
    "dinner",
    "lunch",
    "hungry",
    "dining",
    "takeout",
    "take out",
)

_LODGING_WORDS = (
    "hotel",
    "hotels",
    "motel",
    "lodging",
    "stay",
    "place to stay",
    "vacation rental",
    "airbnb",
    "rv park",
    "campground",
    "resort",
)

_SHOPPING_WORDS = (
    "shopping",
    "shop",
    "store",
    "buy",
    "boutique",
    "grocery",
    "groceries",
    "supermarket",
)

_FITNESS = {
    "yoga_pilates": ("yoga", "pilates", "barre"),
    "martial_arts": ("martial arts", "karate", "jiu jitsu", "bjj", "judo", "taekwondo", "dojo"),
    "gym_fitness": ("gym", "fitness", "crossfit", "workout", "weights"),
    "pickleball": ("pickleball", "tennis court", "racquet"),
}

_CLASS_WORDS = ("lesson", "lessons", "class", "classes", "program", "swim lesson")

# "next event at <venue>", "what's happening at <place>", "live music at X" name a
# specific venue. The layer can't filter events by venue, so listing all events
# would answer a different question -- fall through to the entity-aware path.
_VENUE_AT_RE = re.compile(
    r"\b(?:happening|event|events|class|classes|show|shows|game|games|live music)\s+at\s+\w"
)


def _match_area(text: str) -> str | None:
    for phrase, district in dicts.AREA_DICT.items():
        if phrase in text:
            return district
    return None


def _match_cuisine(text: str) -> str | None:
    # Longest keys first so "ice cream" / "real estate"-style multiword wins.
    for term in sorted(dicts.CUISINE_DICT, key=len, reverse=True):
        if _has(text, term):
            return term
    # Token-level fallback: "taco"/"taqueria" -> mexican, "breweries" -> brewery.
    for cuisine, tokens in dicts.CUISINE_DICT.items():
        if _has_any(text, tokens):
            return cuisine
    return None


def _match_service(text: str) -> str | None:
    for term in sorted(dicts.SERVICE_DICT, key=len, reverse=True):
        if _has(text, term):
            return term
    return None


def _match_symptom(text: str) -> str | None:
    for term in sorted(dicts.SYMPTOM_MAP, key=len, reverse=True):
        if term in text:
            return term
    return None


def _event_window(text: str) -> str | None:
    """Canonical event window from the date phrasing, default 'upcoming'."""
    dr = None
    try:
        dr = extract_date_range(text)
    except Exception:
        dr = None
    if "tonight" in text or "today" in text:
        return "today"
    if "tomorrow" in text:
        return "tomorrow"
    if "this weekend" in text or "weekend" in text:
        return "this_weekend"
    if "next week" in text:
        return "next_week"
    if "this week" in text:
        return "this_week"
    if "next month" in text:
        return "next_month"
    if dr is not None:
        return "range"
    return "upcoming"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def resolve(query: str) -> ResolvedIntent | None:
    """Return the cheapest confident intent, or None to fall through."""
    if not query or not query.strip():
        return None
    t = normalize(query)
    if not t:
        return None

    # 1. Cheapest gas -- highest-confidence utility intent.
    if _GAS_RE.search(t) and (_GAS_INTENT_RE.search(t) or _has(t, "gas")):
        # Require a gas-shaped ask, not an incidental "gas" mention.
        if _GAS_INTENT_RE.search(t) or t.strip() in {"gas", "gas prices", "gas price"}:
            return ResolvedIntent("cheapest_gas", {}, L1)

    # 2. Events -- explicit event signal, optionally with a date window.
    if _has_any(t, _EVENT_WORDS):
        if _VENUE_AT_RE.search(t):
            return None  # venue-specific ("event at X") -> entity-aware path owns it
        window = _event_window(t)
        slots: dict[str, object] = {"window": window}
        if _has_any(t, ("live music", "concert")):
            slots["activity"] = "live_music"
        key = {
            "today": "events_today",
            "tomorrow": "events_today",
            "this_weekend": "events_weekend",
            "this_week": "events_this_week",
            "next_week": "events_next_week",
            "next_month": "events_next_week",
        }.get(window, "events_upcoming")
        return ResolvedIntent(key, slots, L2 if window != "upcoming" else L1)

    # 3. Service lookup -- service term routes to a Provider.subcategory group.
    service = _match_service(t)
    if service is not None:
        slots = {"service": service}
        area = _match_area(t)
        if area:
            slots["area"] = area
            layer = L2
        else:
            layer = L1
        if _OPEN_NOW_RE.search(t):
            slots["open_now"] = True
            layer = L2
        return ResolvedIntent("find_service", slots, layer)

    # 4. Symptom / urgent need -> health listing (never advice).
    symptom = _match_symptom(t)
    if symptom is not None:
        return ResolvedIntent("urgent_care", {"symptom": symptom}, L2)

    # 5. Eat & drink -- cuisine token or generic food word.
    cuisine = _match_cuisine(t)
    if cuisine is not None or _has_any(t, _FOOD_WORDS):
        slots = {}
        layer = L1
        if cuisine is not None:
            slots["cuisine"] = cuisine
            layer = L2
        area = _match_area(t)
        if area:
            slots["area"] = area
            layer = L2
        open_now = bool(_OPEN_NOW_RE.search(t))
        if open_now:
            slots["open_now"] = True
            layer = L2
        key = "eat_open_now" if open_now and cuisine is None and not area else "eat_find"
        return ResolvedIntent(key, slots, layer)

    # 6. Fitness / classes (before lodging so "gym" etc. win).
    for intent_key, terms in _FITNESS.items():
        if _has_any(t, terms):
            slots = {}
            band = dicts.parse_age_band(t)
            if band:
                slots["age_band"] = band
            return ResolvedIntent(intent_key, slots, L1)

    # 7. Kids lessons / classes.
    if _has_any(t, _CLASS_WORDS):
        band = dicts.parse_age_band(t)
        if band or _has_any(t, ("kid", "kids", "child", "children", "youth")):
            return ResolvedIntent(
                "kids_lessons",
                {"age_band": band or "kids"},
                L2,
            )

    # 8. Lodging / stay.
    if _has_any(t, _LODGING_WORDS):
        slots = {}
        area = _match_area(t)
        if area:
            slots["area"] = area
        return ResolvedIntent("lodging_find", slots, L1)

    # 9. Shopping.
    if _has_any(t, _SHOPPING_WORDS):
        slots = {}
        area = _match_area(t)
        if area:
            slots["area"] = area
        return ResolvedIntent("shopping_find", slots, L1)

    # No confident intent -> fall through to existing Tier 2 / Tier 3.
    return None
