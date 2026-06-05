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
    "what is on",  # normalize() expands "whats" -> "what is"
    "what should we do",
    "what should i do",
    "anything fun",
)
_OPEN_NOW_RE = re.compile(
    r"\bopen\s+(now|right now|late|tonight)\b"
    r"|\bopen\s*\?"
    r"|\bopen\s+for\s+(breakfast|lunch|dinner)\b"
    r"|\bwho'?s\s+open\b|\bwho\s+is\s+open\b"
    r"|\bopen\s+to\s+eat\b|\banywhere\s+open\b"
)

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
    "motels",
    "lodging",
    "stay",
    "place to stay",
    "vacation rental",
    "airbnb",
    "rv park",
    "campground",
    "campgrounds",
    "resort",
    "resorts",
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

# On-the-water: explicit water-activity nouns only. Deliberately NOT bare "lake"
# (so "hotels near the lake" stays lodging) -- requires a boat/marina/watercraft
# signal or an explicit launch/ramp.
_WATER_WORDS = (
    "boat",
    "boats",
    "marina",
    "kayak",
    "canoe",
    "paddleboard",
    "paddle board",
    "jet ski",
    "jetski",
    "jet-ski",
    "wave runner",
    "waverunner",
    "watercraft",
    "marine",
    "boat launch",
    "boat ramp",
    "boat rental",
    "boat tour",
    "lake access",
    "fishing",
)
_RENT_WORDS = ("rent", "rental", "rentals", "hire")
_REPAIR_WORDS = ("repair", "fix", "service", "mechanic")

# Strong purchase signal -- when present, a water/park noun is the thing being
# BOUGHT ("buy fishing gear", "buy beach stuff"), so it's a shopping intent, not
# an on-the-water / parks one. Excludes weak "shop"/"store" (those appear in
# "repair shop" / "body shop" without a purchase intent).
_SHOPPING_STRONG = ("buy", "shopping", "grocery", "groceries", "supermarket", "boutique")

# Parks / trails / beaches. Placed after lodging so "rv park" stays lodging.
_PARK_WORDS = (
    "park",
    "parks",
    "trail",
    "trails",
    "trailhead",
    "trailheads",
    "hike",
    "hikes",
    "hiking",
    "beach",
    "beaches",
    "off road",
    "off-road",
    "offroad",
)

# Civic / community resources -- libraries, worship, public services.
_CIVIC_WORDS = (
    "church",
    "churches",
    "worship",
    "synagogue",
    "mosque",
    "temple",
    "library",
    "libraries",
    "city hall",
    "dmv",
    "post office",
    "courthouse",
    "government",
    "non profit",
    "non-profit",
    "nonprofit",
    "community center",
    "food bank",
    "senior center",
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

    # 3. Symptom / urgent need FIRST -- "i need a walk in clinic" must route to
    # urgent_care even when a service term ("clinic") also matches (2026-06-04,
    # 5k-bank validation drop).
    symptom = _match_symptom(t)
    if symptom is not None:
        return ResolvedIntent("urgent_care", {"symptom": symptom}, L2)

    # 3b. Service lookup -- service term routes to a Provider.subcategory group.
    service = _match_service(t)
    if service is not None:
        # Water-adjacent repair terms belong to the on-the-water bucket:
        # "boat mechanic in town" -> boat_repair, not find_service.
        if _has_any(t, _WATER_WORDS) and (
            service in _REPAIR_WORDS or "mechanic" in service or "repair" in service
        ):
            service = None
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

    # 5. Eat & drink -- cuisine token or generic food word.
    cuisine = _match_cuisine(t)
    if "food bank" in t:
        return ResolvedIntent("civic_resources", {}, L1)
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

    # 9. On the water -- boat/marina/watercraft signal. Rent vs repair vs
    # general from the verb; otherwise the on-the-water bucket. Before shopping
    # so "boat repair shop" routes to boat_repair, not shopping (the "shop"
    # token).
    if _has_any(t, _WATER_WORDS) and not _has_any(t, _SHOPPING_STRONG):
        slots = {}
        area = _match_area(t)
        if area:
            slots["area"] = area
        if _has_any(t, _RENT_WORDS):
            key = "boat_rental"
        elif _has_any(t, _REPAIR_WORDS):
            key = "boat_repair"
        else:
            key = "on_the_water"
        layer = L2 if (area or key != "on_the_water") else L1
        return ResolvedIntent(key, slots, layer)

    # 10. Parks / trails / beaches.
    if _has_any(t, _PARK_WORDS) and not _has_any(t, _SHOPPING_STRONG):
        slots = {}
        area = _match_area(t)
        if area:
            slots["area"] = area
        return ResolvedIntent("parks_trails", slots, L2 if slots else L1)

    # 11. Civic / community resources.
    if _has_any(t, _CIVIC_WORDS):
        return ResolvedIntent("civic_resources", {}, L1)

    # 12. Shopping (last broad bucket -- "shop"/"store" are generic, so the
    # specific buckets above win first).
    if _has_any(t, _SHOPPING_WORDS):
        slots = {}
        area = _match_area(t)
        if area:
            slots["area"] = area
        return ResolvedIntent("shopping_find", slots, L1)

    # No confident intent -> fall through to existing Tier 2 / Tier 3.
    return None
