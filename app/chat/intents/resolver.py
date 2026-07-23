"""L0-L3 intent resolver (Ask Hava intent catalog, Phase 1 + Slice 3 L3).

``resolve(query)`` maps a free-text question to a ``ResolvedIntent`` (intent
key + primitive slots + the matcher layer that caught it), or ``None`` when no
intent is confident -- ``None`` means "fall through to the existing Tier 2 /
Tier 3 path", which is the intended behavior, not a failure.

Design rules (master spec §0, §5):
* Cheapest layer that works. L1 keyword/regex first; L2 dictionary slot-fill;
  L3 fuzzy exemplar match (Slice 3, ``app/chat/intents/fuzzy.py``) only after
  every keyword layer has declined.
* Conservative: when unsure, return ``None`` rather than guess. The existing
  router handles everything we don't claim.
* Slots are JSON-friendly primitives (strings / bools) so they can be logged
  and asserted in tests; the query layer re-derives routes from the dicts.

2026-06-11 (intent-efficiency pass): match tables are precomputed at import
(no per-call ``sorted``), ``_word`` patterns are cached, and the L3 fuzzy hook
runs last behind its own kill switch. The L1/L2 contract is byte-identical for
every query those layers already claimed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.chat.intents import dicts
from app.chat.normalizer import normalize
from app.core.slots import extract_date_range

logger = logging.getLogger(__name__)

# Layer labels (for telemetry / tests asserting min_layer).
L1 = "L1"
L2 = "L2"
L3 = "L3"


@dataclass(frozen=True)
class ResolvedIntent:
    intent_key: str
    slots: dict[str, object] = field(default_factory=dict)
    layer: str = L1


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=2048)
def _word(term: str) -> re.Pattern[str]:
    # Cached: the resolver probes the same fixed vocabulary on every call, so
    # compiling per call was pure waste (hot path: ~40 probes per query).
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

# 2026-06-11: "event planner" / "event planning" / "wedding venue" asks are
# service lookups wearing an event word. Without this guard the events branch
# claimed them and answered with an events list (wrong question). With it they
# fall through to the service dict ("event planner" is a SERVICE_DICT key).
_EVENT_SERVICE_SKIP = ("planner", "planners", "planning", "rentals", "rental")

# 2026-06-13 (P1-2 / P2-2 root cause): weather-coping asks ("what should I do when
# it's too hot", "things to do to beat the heat") wear a generic event word
# ("what should i do" / "to do") but are how-do-I-cope questions, not an events
# browse. Without this guard the events branch claimed them and answered with a
# swim-heavy events list (the Aquatic Center over-reliance). With it they fall
# through to Tier 3 for a real "beat the heat" answer.
_EVENT_WEATHER_SKIP = (
    "too hot",
    "beat the heat",
    "beat heat",
    "escape the heat",
    "in the heat",
    "when it's hot",
    "when it is hot",
    "when its hot",
    "stay cool",
    "keep cool",
    "cool off",
    "cool down",
    "when it rains",
    "when it's raining",
    "when it is raining",
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
    # 2026-06-11 expansion
    "bnb",
    "bed and breakfast",
    "extended stay",
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
    # 2026-06-11 expansion: rental nouns users actually type ("rent a pontoon"
    # paid Tier 3 with a boat-rental category live in the catalog).
    "pontoon",
    "pontoons",
    "houseboat",
    "sea doo",
    "seadoo",
    "wakeboard",
    "water ski",
    "tubing",
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
    # 2026-06-06 gap report: "mountian biking" (sic) fell to Tier 3. Bare
    # "bike" stays out ("bike shop" is retail); the -ing/trail forms are
    # unambiguously recreation.
    "biking",
    "mountain biking",
    "bike trail",
    "bike trails",
    # 2026-06-11 expansion: family-outdoor nouns with live catalog coverage.
    "playground",
    "playgrounds",
    "splash pad",
    "disc golf",
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
    # 2026-06-11 expansion
    "food assistance",
    "soup kitchen",
    "mvd",
    "motor vehicle department",
    "social security",
)

_FITNESS = {
    "yoga_pilates": ("yoga", "pilates", "barre"),
    "martial_arts": ("martial arts", "karate", "jiu jitsu", "bjj", "judo", "taekwondo", "dojo"),
    "gym_fitness": ("gym", "fitness", "crossfit", "workout", "weights"),
    "pickleball": ("pickleball", "tennis court", "racquet"),
}

# 2026-06-06 gap report: "what activities can my 8 year old do after school
# hours" paid Tier 3 twice. "activities"/"after school" only reach the
# kids_lessons branch when an age band or kid word is also present, so adult
# "activities" queries still fall through unchanged.
_CLASS_WORDS = (
    "lesson",
    "lessons",
    "class",
    "classes",
    "program",
    "swim lesson",
    "activities",
    "activity",
    "after school",
    "after-school",
)

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


# Longest-first key tables, precomputed once (the per-call ``sorted`` was the
# resolver's single hottest line under profiling -- pure waste on a static dict).
_CUISINE_KEYS_BY_LEN: tuple[str, ...] = tuple(sorted(dicts.CUISINE_DICT, key=len, reverse=True))
_SERVICE_KEYS_BY_LEN: tuple[str, ...] = tuple(sorted(dicts.SERVICE_DICT, key=len, reverse=True))
_SYMPTOM_KEYS_BY_LEN: tuple[str, ...] = tuple(sorted(dicts.SYMPTOM_MAP, key=len, reverse=True))


def _match_cuisine(text: str) -> str | None:
    # Longest keys first so "ice cream" / "real estate"-style multiword wins.
    for term in _CUISINE_KEYS_BY_LEN:
        if _has(text, term):
            return term
    # Token-level fallback: "taco"/"taqueria" -> mexican, "breweries" -> brewery.
    for cuisine, tokens in dicts.CUISINE_DICT.items():
        if _has_any(text, tokens):
            return cuisine
    return None


def _match_service(text: str) -> str | None:
    for term in _SERVICE_KEYS_BY_LEN:
        if _has(text, term):
            return term
    return None


def _match_symptom(text: str) -> str | None:
    for term in _SYMPTOM_KEYS_BY_LEN:
        if term in text:
            return term
    return None


# Known Program.activity_category values (see the programs loaders): kids,
# arts, food, recreation, aquatics, dance. Token -> category slug.
_CLASS_TOPIC_TOKENS: dict[str, str] = {
    "art": "arts",
    "arts": "arts",
    "craft": "arts",
    "crafts": "arts",
    "painting": "arts",
    "pottery": "arts",
    "cook": "food",
    "cooking": "food",
    "baking": "food",
    "swim": "aquatics",
    "swimming": "aquatics",
    "aqua": "aquatics",
    "aquatic": "aquatics",
    "water": "aquatics",
    "dance": "dance",
    "dancing": "dance",
}


def _match_class_topic(text: str) -> str | None:
    for tok, slug in _CLASS_TOPIC_TOKENS.items():
        if _has(text, tok):
            return slug
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
        # Concrete dates from extract_date_range ("saturday", "July 25",
        # "2026-07-25") ride along inside the window token. The old bare
        # "range" token had no branch in _event_window_dates, so the parsed
        # date was silently discarded and every "what's on <day>" answer
        # fell back to the upcoming window anchored on *today* — a Saturday
        # ask rendered Thursday's calendar.
        return f"range:{dr['start'].isoformat()}:{dr['end'].isoformat()}"
    return "upcoming"


_WINDOW_TO_EVENT_KEY: dict[str, str] = {
    "today": "events_today",
    "tomorrow": "events_today",
    "this_weekend": "events_weekend",
    "this_week": "events_this_week",
    "next_week": "events_next_week",
    "next_month": "events_next_week",
}


def _event_intent_for(t: str, *, extra_slots: dict[str, object] | None = None,
                      layer: str | None = None) -> ResolvedIntent:
    """Shared events resolution: window -> intent key (+ live-music slot).

    Used by the L1/L2 events branch and by the L3 "_events" pseudo-intent so
    both paths derive identical keys/slots from the date phrasing.
    """
    window = _event_window(t)
    slots: dict[str, object] = {"window": window}
    # 2026-06-30 audit A2: catch the live-music phrasings the fuzzy "_events"
    # exemplars reach on too ("live bands", "live entertainment") so they filter
    # to real music, not the whole day's calendar.
    if _has_any(t, ("live music", "live band", "live bands", "live entertainment",
                    "concert", "concerts")):
        slots["activity"] = "live_music"
    if extra_slots:
        slots.update(extra_slots)
    key = _WINDOW_TO_EVENT_KEY.get(window, "events_upcoming")
    if layer is None:
        layer = L2 if window != "upcoming" else L1
    return ResolvedIntent(key, slots, layer)


_VOCAB_SOURCES: tuple[tuple[str, ...], ...] = (
    _EVENT_WORDS,
    _FOOD_WORDS,
    _LODGING_WORDS,
    _SHOPPING_WORDS,
    _WATER_WORDS,
    _RENT_WORDS,
    _REPAIR_WORDS,
    _SHOPPING_STRONG,
    _PARK_WORDS,
    _CIVIC_WORDS,
    _CLASS_WORDS,
)

_category_vocab_cache: frozenset[str] | None = None


def category_vocabulary() -> frozenset[str]:
    """Every word that can trigger a category/listing resolution.

    Used by ``runtime._entity_match_spurious`` to decide whether an entity
    match is explained entirely by generic category tokens ("electrician" ->
    "Morgan Electric") rather than by a distinctive name token ("mudshark").
    Built lazily from the same dicts/tuples the resolver matches against, so
    new dictionary entries are covered automatically.
    """
    global _category_vocab_cache
    if _category_vocab_cache is not None:
        return _category_vocab_cache
    words: set[str] = set()

    def _add(phrase: str) -> None:
        for w in re.split(r"[^a-z0-9]+", phrase.lower()):
            if w:
                words.add(w)

    for term, route in dicts.SERVICE_DICT.items():
        _add(term)
        for tok in route.name_tokens:
            _add(tok)
    for term, tokens in dicts.CUISINE_DICT.items():
        _add(term)
        for tok in tokens:
            _add(tok)
    for term in dicts.SYMPTOM_MAP:
        _add(term)
    for source in _VOCAB_SOURCES:
        for term in source:
            _add(term)
    for terms in _FITNESS.values():
        for term in terms:
            _add(term)
    _category_vocab_cache = frozenset(words)
    return _category_vocab_cache


# ---------------------------------------------------------------------------
# L3 fuzzy hook (Slice 3)
# ---------------------------------------------------------------------------


def _dynamic_slots_for(intent_key: str, t: str, slots: dict[str, object]) -> dict[str, object]:
    """Layer the cheap L2 slot extractors over an L3 fixed-slot dict.

    Keeps L3 answers exactly as grounded as L2 ones: the fuzzy layer picks the
    intent; the slots still come from the same controlled extractors.
    """
    out = dict(slots)
    if intent_key in ("find_service", "eat_find", "lodging_find", "shopping_find",
                      "boat_rental", "boat_repair", "on_the_water", "parks_trails"):
        area = _match_area(t)
        if area and "area" not in out:
            out["area"] = area
    if intent_key in ("find_service", "eat_find"):
        if _OPEN_NOW_RE.search(t):
            out["open_now"] = True
    if intent_key == "eat_find" and "cuisine" not in out:
        cuisine = _match_cuisine(t)
        if cuisine is not None:
            out["cuisine"] = cuisine
    if intent_key == "kids_lessons":
        band = dicts.parse_age_band(t)
        if band:
            out["age_band"] = band
        out.setdefault("age_band", "kids")
    if intent_key == "classes_find":
        topic = _match_class_topic(t)
        if topic and "topic" not in out:
            out["topic"] = topic
    return out


def _try_l3(t: str) -> ResolvedIntent | None:
    """L3 fuzzy exemplar match -- last resort before falling through.

    Best-effort and flag-gated inside ``fuzzy``; any exception falls through
    so the resolver contract ("None means the legacy path answers") holds.
    """
    try:
        from app.chat.intents import fuzzy

        hit = fuzzy.match_l3(t, category_vocabulary())
    except Exception:
        logger.exception("resolver: L3 fuzzy probe failed")
        return None
    if hit is None:
        return None
    intent_key, fixed = hit
    if intent_key == "_events":
        return _event_intent_for(t, extra_slots=fixed, layer=L3)
    slots = _dynamic_slots_for(intent_key, t, fixed)
    return ResolvedIntent(intent_key, slots, L3)


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
    # 2026-06-11: service asks wearing an event word ("event planner") skip
    # this branch and reach the service dict below.
    if (
        _has_any(t, _EVENT_WORDS)
        and not _has_any(t, _EVENT_SERVICE_SKIP)
        and not _has_any(t, _EVENT_WEATHER_SKIP)
    ):
        if _VENUE_AT_RE.search(t):
            return None  # venue-specific ("event at X") -> entity-aware path owns it
        return _event_intent_for(t)

    # 3. Symptom / urgent need FIRST -- "i need a walk in clinic" must route to
    # urgent_care even when a service term ("clinic") also matches (2026-06-04,
    # 5k-bank validation drop). 2026-06-11: "refill" means a PRESCRIPTION
    # refill unless the tank being refilled is in the query ("propane refill"
    # must reach the propane service route, not a pharmacy listing).
    symptom = _match_symptom(t)
    if symptom == "refill" and _has(t, "propane"):
        symptom = None
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
            # 2026-06-11: per-trade water services stay find_service -- a
            # cracked boat-trailer or boat detail belongs to the trade dict
            # ("trailer repair", "detailing"), not the generic boat_repair
            # bucket. Only the GENERIC repair words defer to the water branch.
            if service in ("trailer repair", "detailing", "boat detailing",
                           "mobile detailing", "auto detailing", "car detailing",
                           "detail shop", "windshield repair", "windshield replacement"):
                pass
            else:
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

    # 5. Eat & drink -- cuisine token or generic food word. Community food
    # programs carve out first: their "food" token must not read as dining
    # ("food bank" pre-dates this; "food assistance" / "soup kitchen" joined
    # 2026-06-11 with the civic widening).
    cuisine = _match_cuisine(t)
    if "food bank" in t or "food assistance" in t or "soup kitchen" in t:
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

    # 7. Kids lessons / classes. Civic phrasings ("senior center activities")
    # defer to the civic bucket — "activities"/"activity" joined _CLASS_WORDS
    # in the 2026-06-06 widening and must not outrank a civic venue mention.
    if _has_any(t, _CLASS_WORDS) and not _has_any(t, _CIVIC_WORDS):
        band = dicts.parse_age_band(t)
        if band or _has_any(t, ("kid", "kids", "child", "children", "youth")):
            return ResolvedIntent(
                "kids_lessons",
                {"age_band": band or "kids"},
                L2,
            )
        # 7b. General classes browse (2026-06-07): explicit class/lesson/
        # program words with no age signal ("what classes does parks and
        # recreation offer", "any art classes this week" — 3x/9.6k tokens in
        # the 30-day window). Deliberately NOT triggered by bare
        # "activities"/"activity" (too broad). Topic narrows by
        # Program.activity_category when a known topic token is present.
        if _has_any(t, ("class", "classes", "lesson", "lessons", "program", "programs")):
            slots = {}
            topic = _match_class_topic(t)
            if topic:
                slots["topic"] = topic
            return ResolvedIntent("classes_find", slots, L2 if topic else L1)

    # 8. Lodging / stay.
    # "stay cool" / "keep cool" are weather-coping asks, not lodging — the "stay"
    # token must not route them to hotels (P2-2, 2026-06-13).
    if _has_any(t, _LODGING_WORDS) and not _has_any(t, _EVENT_WEATHER_SKIP):
        slots = {}
        area = _match_area(t)
        if area:
            slots["area"] = area
        return ResolvedIntent("lodging_find", slots, L1)

    # 9. On the water -- boat/marina/watercraft signal. Rent vs repair vs
    # general from the verb; otherwise the on-the-water bucket. Before shopping
    # so "boat repair shop" routes to boat_repair, not shopping (the "shop"
    # token). 2026-06-11: detailing/wrap/tint asks about a boat are trade
    # lookups, not water browses -- deflect so the service dict / L3 owns them
    # ("boat detail and wash" must surface detailers, not a lake listing).
    if (
        _has_any(t, _WATER_WORDS)
        and not _has_any(t, _SHOPPING_STRONG)
        and not _has_any(t, ("detail", "detailing", "wrap", "wrapped", "tint"))
    ):
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

    # 13. L3 fuzzy (Slice 3): exemplar match for the paraphrases every keyword
    # layer above declined ("my sink is leaking", "locked out of my car").
    # Kill switch INTENT_L3_FUZZY; INTENT_L3_SHADOW logs would-be claims
    # without claiming. urgent_care / cheapest_gas can never finalize here.
    l3 = _try_l3(t)
    if l3 is not None:
        return l3

    # No confident intent -> fall through to existing Tier 2 / Tier 3.
    return None
