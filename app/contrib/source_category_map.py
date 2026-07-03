"""Source Category Crosswalk — the single authority for "categorize the way the
source does".

golakehavasu (the CVB) and River Scene each tag every listing/event with their
own category. Historically our loaders collapsed that tag to a coarse Tier-1
bucket (or threw it away) and let a Google-Places-type guess decide the leaf.
This module inverts that: the *source's* category maps directly to an Ask Hava
**leaf** (businesses) or **event-category** (events), and that mapping is the
primary signal — overriding the Google guess.

See ``docs/audits/2026-07/PARITY_AND_COMPLETENESS_PLAN_2026-07-03.md``.

Two guarantees this module is built to support:
  * **Parity** — every recognised source category resolves to a real leaf /
    event-category.
  * **No silent drift** — ``KNOWN_BUSINESS_SOURCE_CATEGORIES`` /
    ``KNOWN_EVENT_SOURCE_CATEGORIES`` enumerate everything we've mapped, so a CI
    test can assert every category observed in the wild is present here; a new,
    unmapped source category fails CI instead of defaulting silently.
"""

from __future__ import annotations

import re

from app.contrib.name_leaf_signals import leaf_from_name

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalize_source_category(raw: str | None) -> str:
    """Fold a source's raw category label to a canonical lookup key.

    "Restaurant/Bar" -> "restaurant bar"; "Boat Rental With Captain" ->
    "boat rental with captain"; "Family-Fun" -> "family fun".
    """
    if not raw:
        return ""
    s = raw.strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[-/,_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Businesses: source category -> Ask Hava leaf slug
# ---------------------------------------------------------------------------

# Unambiguous 1:1 mappings (the source tag alone pins the leaf).
_BUSINESS_CATEGORY_TO_LEAF: dict[str, str] = {
    # -- On the Water --
    "charters": "boat-tours-and-charters",
    "boat rental with captain": "boat-tours-and-charters",
    "water tours": "boat-tours-and-charters",
    "fishing": "fishing-charters-and-guides",
    "fishing guide": "fishing-charters-and-guides",
    "launch ramps and marinas": "marinas-and-launch-ramps",
    "beaches and swimming": "beaches-and-swim-areas",
    "boat in beaches and campsites": "beaches-and-swim-areas",
    # -- Outdoors & Recreation --
    "parks": "parks-and-playgrounds",
    "dog parks": "dog-parks",
    "hiking": "hiking-trails",
    "easy hikes": "hiking-trails",
    # long-form CVB tags (data-dms-category-name uses the verbose labels)
    "moderate hikes": "hiking-trails",
    "moderate hikes with climbing": "hiking-trails",
    "difficult hikes": "hiking-trails",
    "difficult hikes with long slopes or scrambling": "hiking-trails",
    "walks": "hiking-trails",
    "camping": "rv-parks-and-campgrounds",
    "ohv": "off-road-and-ohv",
    "off road": "off-road-and-ohv",
    "offroad": "off-road-and-ohv",
    "birding": "wildlife-and-nature",
    "golf": "golf-courses",
    # -- Things to Do & Attractions --
    "attractions": "landmarks-and-sights",
    "family fun": "family-fun-and-arcades",
    "entertainment": "family-fun-and-arcades",
    "venues": "event-venues",
    "tours": "tours-and-sightseeing",
    "outdoor land tours": "tours-and-sightseeing",
    "air tours": "tours-and-sightseeing",
    "gaming and casinos": "casinos-and-gaming",
    "movie theaters": "theaters-and-cinema",
    "performing arts": "theaters-and-cinema",
    # -- Eat & Drink --
    "restaurant bar": "restaurants",
    "diner": "restaurants",
    "breweries and wine bar": "bars-and-breweries",
    # -- Lodging --
    "lodging": "hotels-and-motels",
    "hotels motels suites": "hotels-and-motels",
    "resorts": "hotels-and-motels",
    "rv parks": "rv-parks-and-campgrounds",
    "vacation rentals condos": "vacation-rentals",
    # -- Shopping / Transportation --
    "transportation": "shuttles-and-transportation",
}

# Categories where the source tag is generic and the business *name* decides the
# leaf (Casey's decision #4, 2026-07-03). Each maps to a (default_leaf) used when
# the name gives no signal.
_AMBIGUOUS_BUSINESS_DEFAULTS: dict[str, str] = {
    "water sports": "jet-ski-and-watersports",
    "boating": "boat-and-watercraft-rentals",
    "guided tour": "tours-and-sightseeing",
    "activities": "tours-and-sightseeing",
    "shopping": "gifts-and-boutiques",
}

# Name overrides for the "shopping" bucket (retail sub-routing).
_SHOPPING_NAME_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(clothing|apparel|boutique\s+clothing|outfitter|western\s+wear)\b", re.I), "clothing-and-apparel"),
    (re.compile(r"\b(jewelry|jeweler|jewellers?|diamond)\b", re.I), "jewelry"),
    (re.compile(r"\b(hardware|home\s+improvement|ace|true\s?value|lumber)\b", re.I), "hardware-and-home-improvement"),
    (re.compile(r"\b(furniture|mattress)\b", re.I), "furniture-and-mattress"),
    (re.compile(r"\b(florist|flowers?)\b", re.I), "florists"),
    (re.compile(r"\b(sporting\s+goods|sports\s+shop|tackle|outdoor\s+gear)\b", re.I), "sporting-goods"),
    (re.compile(r"\b(thrift|consignment|resale)\b", re.I), "thrift-and-consignment"),
)

# The complete set of business source categories we recognise (for the CI guard).
KNOWN_BUSINESS_SOURCE_CATEGORIES: frozenset[str] = frozenset(_BUSINESS_CATEGORY_TO_LEAF) | frozenset(
    _AMBIGUOUS_BUSINESS_DEFAULTS
)


def map_business_leaf(
    source_category: str | None,
    *,
    name: str | None = None,
    source: str = "go_lake_havasu",
) -> str | None:
    """Resolve a source category (+ optional name) to an Ask Hava leaf slug.

    Precedence within this function:
      1. name signal is allowed to *lift* an on-the-water tag to charter/tour/
         fishing/kayak/marina (a captained tour tagged "boating" should not sit
         in plain rentals);
      2. otherwise the direct crosswalk;
      3. for ambiguous tags, the name signal decides, falling back to the tag's
         default leaf.

    Returns ``None`` when the category is unrecognised (caller/CI must handle).
    """
    key = normalize_source_category(source_category)
    if not key:
        return None

    name_leaf = leaf_from_name(name)

    # Ambiguous tags: name decides, else default. (decision #4)
    if key in _AMBIGUOUS_BUSINESS_DEFAULTS:
        if key == "shopping":
            for pat, leaf in _SHOPPING_NAME_RULES:
                if name and pat.search(name):
                    return leaf
            return _AMBIGUOUS_BUSINESS_DEFAULTS[key]
        if name_leaf is not None:
            return name_leaf
        # "boating" with a marina in the name is a marina even without a name-leaf
        # hit above (leaf_from_name already covers marina, so this is belt-and-suspenders).
        return _AMBIGUOUS_BUSINESS_DEFAULTS[key]

    direct = _BUSINESS_CATEGORY_TO_LEAF.get(key)
    if direct is None:
        return None

    # A name signal may lift an on-the-water tag to a more specific water leaf,
    # e.g. a "water tours" listing named "...Kayak Tours" -> kayak-and-paddle.
    _WATER_LEAVES = {
        "boat-and-watercraft-rentals",
        "boat-tours-and-charters",
        "fishing-charters-and-guides",
        "kayak-and-paddle",
        "jet-ski-and-watersports",
        "marinas-and-launch-ramps",
    }
    if name_leaf is not None and direct in _WATER_LEAVES:
        return name_leaf

    return direct


# ---------------------------------------------------------------------------
# Events: source category -> canonical event-category (~22 values)
# ---------------------------------------------------------------------------

# Canonical event category -> the source tokens (normalised) that fold into it.
_EVENT_CATEGORY_SOURCES: dict[str, tuple[str, ...]] = {
    "boating-and-lake": ("boating", "on the lake", "on the river", "boat tours", "boat show", "yacht club"),
    "racing-and-motorsports": ("racing", "off road", "car show", "rodeo"),
    "air-show": ("air show",),
    "music": ("music", "bands", "new years eve bands"),
    "festival": ("festival", "london bridge days", "fair", "community fair", "spring break"),
    "arts-and-theater": (
        "theater", "art", "art fair", "arts and crafts", "creative comrades", "fashion show",
    ),
    "comedy": ("comedy show", "comedy"),
    "film": ("movies", "film"),
    "food-and-drink": ("dinner", "food", "adult beverages", "bars", "potluck"),
    "farmers-market": ("farmers market", "farmers"),
    "family-and-kids": ("family party", "youth", "cub scouts", "bunco bingo", "adult game night"),
    "sports-and-fitness": (
        "sports event", "fitness", "gyms", "dance", "special olympics", "dodgeball", "sports",
    ),
    "education-and-lecture": (
        "lecture", "educational", "workshops", "book signing", "library", "school",
        "summer camp", "summer school", "telesis school", "high school",
        "web design digital marketing",
    ),
    "health-and-wellness": ("health", "health fair", "wellness", "awareness"),
    "community-and-civic": (
        "chamber of commerce", "networking", "open to public", "community",
        "fire department", "first friday",
    ),
    "fundraiser-and-charity": ("fundraiser",),
    "holiday": ("holiday", "christmas", "new years eve", "halloween", "easter", "fireworks"),
    "faith": ("church", "ceremony"),
    "military-and-veterans": ("military", "veterans military"),
    "museum": ("museum of history", "gem show", "museum"),
    "outdoors-and-camping": ("outdoors", "camping"),
    "pets": ("pets",),
    "pageant": ("pageant",),
    "shopping": ("shopping",),
    "senior": ("assisted living", "senior"),
    "misc": ("events", "select category", "uncategorized"),
}

# Inverted lookup: source token -> canonical event category.
_EVENT_SOURCE_TO_CATEGORY: dict[str, str] = {
    src: canonical for canonical, srcs in _EVENT_CATEGORY_SOURCES.items() for src in srcs
}

KNOWN_EVENT_SOURCE_CATEGORIES: frozenset[str] = frozenset(_EVENT_SOURCE_TO_CATEGORY)
CANONICAL_EVENT_CATEGORIES: frozenset[str] = frozenset(_EVENT_CATEGORY_SOURCES)


def map_event_category(source_category: str | None) -> str | None:
    """Resolve a source event-category to a canonical event category.

    Returns ``None`` when unrecognised so the CI guard / reconciliation job can
    flag it. Note ``"misc"`` is a *recognised* landing for genuinely
    uncategorised source tags, distinct from ``None`` (unknown tag).
    """
    key = normalize_source_category(source_category)
    if not key:
        return None
    return _EVENT_SOURCE_TO_CATEGORY.get(key)


def derive_event_category(tags: list[str] | None) -> str | None:
    """Pick the best canonical event category from a list of source tags/labels.

    An event usually carries several tags (its source category plus keyword
    tags). Prefer the first *specific* canonical hit; fall back to ``"misc"``
    only if that's all that matched; ``None`` if nothing mapped. Used to stamp
    ``Event.category`` at approval time.
    """
    if not tags:
        return None
    saw_misc = False
    for tag in tags:
        mapped = map_event_category(tag)
        if mapped is None:
            continue
        if mapped == "misc":
            saw_misc = True
            continue
        return mapped
    return "misc" if saw_misc else None


# ---------------------------------------------------------------------------
# Locality / region (exclusion gate — Casey's decision #2, Lake Havasu only)
# ---------------------------------------------------------------------------

HAVASU_CORE = "havasu-core"

# Source location tags / place tokens -> region. Anything not Havasu-core is
# out-of-area and excluded at ingest (never imported).
_REGION_TOKENS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(laughlin|bullhead\s*city|bullhead)\b", re.I), "laughlin-bullhead"),
    (re.compile(r"\bneedles\b", re.I), "needles"),
    (re.compile(r"\bparker\b", re.I), "parker"),
    (re.compile(r"\boatman\b", re.I), "oatman"),
    (re.compile(r"\b(kingman|golden\s+valley)\b", re.I), "kingman"),
    (re.compile(r"\b(hoover\s+dam|grand\s+canyon|las\s+vegas)\b", re.I), "other-daytrip"),
)

OUT_OF_AREA_REGIONS: frozenset[str] = frozenset(
    r for _pat, r in _REGION_TOKENS
)

OUTSIDE_SERVICE_AREA_REASON = "outside-service-area"


def resolve_region(*signals: str | None) -> str:
    """Classify a listing's region from any location signals (tags, address,
    city). Returns an out-of-area region slug if *any* signal matches an
    out-of-area token, else ``HAVASU_CORE``.
    """
    for sig in signals:
        if not sig:
            continue
        for pat, region in _REGION_TOKENS:
            if pat.search(sig):
                return region
    return HAVASU_CORE


def is_out_of_area(region: str | None) -> bool:
    """True when the region is anything other than Havasu-core (i.e. excluded)."""
    return bool(region) and region != HAVASU_CORE
