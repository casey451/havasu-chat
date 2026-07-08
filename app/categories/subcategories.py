"""Second-level subcategory taxonomy + backfill mapping (P0 Task 2).

The seven master buckets (``app/v1/categories.py``) were a dead end: a single
``/categories/services`` page dumped ~1,500 mixed listings with no way to
narrow. This module adds the real second level the UI review asked for.

Design (from the P0 brief's first-pass map):

* Each master bucket owns a small set of **subcategory groups** (e.g. Services →
  Home Services · Auto · Health & Medical · Professional · Pets · Beauty ·
  Storage). These are the chips on the category landing page and each is its own
  SEO URL ``/lake-havasu/{subcategory}``.
* ``Provider.subcategory`` stores one group slug per row. ``derive_subcategory``
  computes it from the strongest available signal (Google primary type → Google
  secondary types → legacy ``Provider.category`` → curated ``sub_trades``); it is
  the backfill rule and the on-ingest rule.

Storage lives under **Services**, not Recreation (brief §2). A few groups beyond
the brief's first pass (``civic-community``) exist so real rows — churches,
libraries, non-profits — get a real label instead of falling back to the bucket.

Unmapped rows return ``None``: the landing page shows them under an "All" chip
rather than mislabeling them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.v1.categories import BUCKET_SLUG_REDIRECTS


@dataclass(frozen=True)
class Subcategory:
    """One second-level group under a master bucket.

    ``slug`` is the SEO/URL token (``/lake-havasu/{slug}``) and the value stored
    in ``Provider.subcategory``. ``bucket_id`` ties back to ``MASTER_BUCKETS``.
    """

    slug: str
    label: str
    bucket_id: str
    one_liner: str


# ---------------------------------------------------------------------------
# Taxonomy — bucket_id → ordered subcategory groups (chip order is page order)
# ---------------------------------------------------------------------------

_SUBCATEGORIES: tuple[Subcategory, ...] = (
    # -- Food & Drink --
    Subcategory("restaurants", "Restaurants", "food-drink", "Sit-down spots and local kitchens."),
    Subcategory("bars-breweries", "Bars & Breweries", "food-drink", "Taprooms, pubs, and wine bars."),
    Subcategory("cafes-coffee", "Cafés & Coffee", "food-drink", "Coffee, bakeries, and light bites."),
    Subcategory("quick-bites", "Quick Bites", "food-drink", "Fast, casual, and takeout."),
    # -- Recreation & Outdoors (Storage intentionally NOT here) --
    Subcategory("on-the-water", "Lake Life", "recreation-outdoors", "Marinas, launches, rentals."),
    # Marine trade split out from the recreation "on-the-water" bucket so boat
    # businesses get their own pages (2026-06-13 audit). All map to the
    # ``on-the-water`` primary; watersports *rentals* stay under on-the-water.
    Subcategory("marine-dealers", "Boat Dealers", "recreation-outdoors", "New and used boat sales."),
    Subcategory("marine-repair", "Boat Repair & Mechanics", "recreation-outdoors", "Marine service, repair, and mechanics."),
    Subcategory("marine-supply", "Marine Supply & Stores", "recreation-outdoors", "Parts, accessories, and marine retail."),
    Subcategory("trails-offroad", "Trails & Off-road", "recreation-outdoors", "Hiking and off-road routes."),
    Subcategory("parks-beaches", "Parks & Beaches", "recreation-outdoors", "City parks and shoreline."),
    Subcategory("golf", "Golf", "recreation-outdoors", "Courses and driving ranges."),
    Subcategory("disc-golf", "Disc Golf", "recreation-outdoors", "Disc golf courses and baskets."),
    Subcategory("biking", "Biking", "recreation-outdoors", "Trails, shops, and rentals."),
    # -- Sports, Fitness & Classes --
    Subcategory("gyms", "Gyms", "sports-fitness", "Fitness centers and weight rooms."),
    Subcategory("racquet-sports", "Pickleball & Tennis", "sports-fitness", "Courts, clubs, and leagues."),
    Subcategory("martial-arts", "Martial Arts", "sports-fitness", "Dojos and self-defense studios."),
    Subcategory("studios", "Studios", "sports-fitness", "Yoga, pilates, and dance."),
    Subcategory("kids-lessons", "Kids' Lessons", "sports-fitness", "Classes and youth programs."),
    # -- Shopping --
    Subcategory("boutiques", "Boutiques", "shopping", "Apparel and local boutiques."),
    Subcategory("home-goods", "Home Goods", "shopping", "Furniture, decor, and hardware."),
    Subcategory("specialty", "Specialty", "shopping", "Specialty and hobby shops."),
    Subcategory("markets", "Markets", "shopping", "Grocers and markets."),
    # -- Services (Storage lives here, per brief §2) --
    Subcategory("home-services", "Home Services", "services", "HVAC, plumbing, electrical, roofing, cleaning."),
    Subcategory("auto", "Auto", "services", "Repair, body, tires, RV & gas."),
    Subcategory("health-medical", "Health & Medical", "services", "Dental, vision, clinics, chiro."),
    Subcategory("professional", "Professional", "services", "Legal, insurance, real estate, financial."),
    Subcategory("pets", "Pets", "services", "Vets, grooming, boarding."),
    Subcategory("beauty", "Beauty & Personal Care", "services", "Hair, nails, barber, lashes."),
    Subcategory("storage", "Storage", "services", "Self-storage and RV/boat storage."),
    Subcategory("civic-community", "Civic & Community", "services", "Libraries, worship, non-profits, public services."),
    # -- Stay --
    Subcategory("hotels", "Hotels", "stay", "Hotels, motels, and resorts."),
    Subcategory("vacation-rentals", "Vacation Rentals", "stay", "Short-term and vacation stays."),
    Subcategory("rv-parks", "RV Parks", "stay", "RV parks and campgrounds."),
    # -- Events (provider-side venues; calendar events are a separate feed) --
    Subcategory("attractions", "Attractions", "events", "Museums, galleries, and tours."),
    Subcategory("venues", "Venues", "events", "Event and live-music venues."),
)

_BY_SLUG: dict[str, Subcategory] = {s.slug: s for s in _SUBCATEGORIES}

# plural ``/categories/{route}`` slug → master bucket id, for the bucket
# destinations the home rows / topbar link to. Inverse of BUCKET_SLUG_REDIRECTS.
_ROUTE_TO_BUCKET: dict[str, str] = {
    dest.rsplit("/", 1)[-1]: bucket_id for bucket_id, dest in BUCKET_SLUG_REDIRECTS.items()
}


def subcategory_by_slug(slug: str | None) -> Subcategory | None:
    if not slug:
        return None
    return _BY_SLUG.get(slug.strip().lower())


def subcategories_for_bucket(bucket_id: str) -> list[Subcategory]:
    return [s for s in _SUBCATEGORIES if s.bucket_id == bucket_id]


def bucket_for_category_route(route_slug: str | None) -> str | None:
    """Master bucket a plural ``/categories/{route}`` page belongs to, if any."""
    if not route_slug:
        return None
    return _ROUTE_TO_BUCKET.get(route_slug.strip().lower())



# ---------------------------------------------------------------------------
# Backfill / on-ingest derivation
# ---------------------------------------------------------------------------
#
# Signal precedence: a specific Google type ("plumber") beats a broad legacy
# bucket ("home_services"). We check the most specific signal first and stop at
# the first hit. ``None`` means "leave unlabeled" — never guess a bucket-wide
# default, that's exactly the "everything is Services" bug we're removing.

# Google primary/secondary type token → subcategory slug. Tokens are matched as
# substrings against lowercased Google type strings, so "italian_restaurant"
# matches "restaurant".
_TYPE_TO_SUBCAT: tuple[tuple[str, str], ...] = (
    # order matters: more specific tokens earlier
    ("brewery", "bars-breweries"),
    ("wine_bar", "bars-breweries"),
    ("pub", "bars-breweries"),
    # Guard the broad "bar" token against substring collisions before it runs:
    # "barber_shop" and "barbecue_restaurant" both contain "bar" (prod bug — barber
    # shops were filing as bars-breweries). These must be checked first.
    ("barber", "beauty"),
    ("barbecue", "restaurants"),
    ("barbeque", "restaurants"),
    ("bar", "bars-breweries"),
    ("night_club", "bars-breweries"),
    ("coffee", "cafes-coffee"),
    ("cafe", "cafes-coffee"),
    ("bakery", "cafes-coffee"),
    ("tea", "cafes-coffee"),
    ("fast_food", "quick-bites"),
    ("meal_takeaway", "quick-bites"),
    ("meal_delivery", "quick-bites"),
    ("ice_cream", "quick-bites"),
    ("juice", "quick-bites"),
    # Food trucks match ONLY on the full "food_truck"/"food truck" bigram —
    # never a bare "truck" token. Prod bug (2026-06-05): "A Toe Truck" (a
    # towing company swept up by the food_drink discovery sweep's "food
    # trucks" keyword) carried legacy category="food_drink" and, with no
    # specific type rule, fell through to the legacy tier and filed as
    # restaurants/eat-drink. The tow/roadside rules below (services block)
    # now classify it at the stronger type tier; this bigram keeps genuine
    # food trucks in the food bucket.
    ("food_truck", "quick-bites"),
    ("food truck", "quick-bites"),
    ("restaurant", "restaurants"),
    ("diner", "restaurants"),
    # recreation
    ("marina", "on-the-water"),
    ("boat", "on-the-water"),
    ("harbor", "on-the-water"),
    ("ferry", "on-the-water"),
    ("fishing", "on-the-water"),
    # disc golf before plain golf: "disc golf course" contains "golf", and
    # first-match-wins, so the more specific token must come first.
    ("disc_golf", "disc-golf"),
    ("disc golf", "disc-golf"),
    ("golf", "golf"),
    ("bicycle", "biking"),
    ("bike", "biking"),
    ("hiking", "trails-offroad"),
    ("trail", "trails-offroad"),
    ("off_road", "trails-offroad"),
    ("beach", "parks-beaches"),
    # Overnight-stay types must outrank the bare "park" substring rule below:
    # "rv_park" CONTAINS "park", and first-match-wins, so the stay block's own
    # rv_park/campground entries (line ~300) were unreachable — RV parks and
    # campgrounds filed as parks-beaches instead of rv-parks (→ lodging).
    ("rv_park", "rv-parks"),
    ("campground", "rv-parks"),
    ("park", "parks-beaches"),
    # sports/fitness
    ("pickleball", "racquet-sports"),
    ("tennis", "racquet-sports"),
    ("martial", "martial-arts"),
    ("karate", "martial-arts"),
    ("yoga", "studios"),
    ("pilates", "studios"),
    ("dance", "studios"),
    ("gym", "gyms"),
    ("fitness", "gyms"),
    # shopping
    ("clothing", "boutiques"),
    ("boutique", "boutiques"),
    ("apparel", "boutiques"),
    ("furniture", "home-goods"),
    ("home_goods", "home-goods"),
    ("hardware", "home-goods"),
    ("home_improvement", "home-goods"),
    ("grocery", "markets"),
    ("supermarket", "markets"),
    ("farmers_market", "markets"),
    ("gift", "specialty"),
    ("sporting_goods", "specialty"),
    ("book_store", "specialty"),
    ("store", "specialty"),
    # services
    ("self_storage", "storage"),
    ("storage", "storage"),
    ("plumber", "home-services"),
    ("electrician", "home-services"),
    ("hvac", "home-services"),
    ("roofing", "home-services"),
    ("roofer", "home-services"),
    ("landscap", "home-services"),
    ("contractor", "home-services"),
    ("cleaning", "home-services"),
    ("pest_control", "home-services"),
    ("painter", "home-services"),
    ("car_repair", "auto"),
    # Tow / roadside trades are decisively AUTO at the type tier. Without
    # these rules a tow company had NO type-tier hit, so its (often wrong)
    # legacy discovery-domain category decided the bucket — the "A Toe
    # Truck in Eat & Drink" prod bug. The specific trade signal must beat
    # the coarse legacy label.
    ("towing", "auto"),
    ("tow_truck", "auto"),
    ("tow truck", "auto"),
    ("wrecker", "auto"),
    ("roadside", "auto"),
    ("auto", "auto"),
    ("tire", "auto"),
    ("car_wash", "auto"),
    ("car_dealer", "auto"),
    # Gas stations are auto-rv-fuel, but most also carry "convenience_store" /
    # "store" / "food" array tokens, so without an explicit primary-type rule they
    # fell to shopping-essentials (2026-06-05 patrol: ~15 of the 0.95 flags —
    # Chevron, Shell, Circle K, 76, ...). Needle is "gas_station" not bare "gas"
    # so it can't swallow "gastropub" and friends.
    ("gas_station", "auto"),
    ("rv_", "auto"),
    ("mechanic", "auto"),
    ("dentist", "health-medical"),
    ("dental", "health-medical"),
    ("doctor", "health-medical"),
    ("physician", "health-medical"),
    ("hospital", "health-medical"),
    ("clinic", "health-medical"),
    ("pharmacy", "health-medical"),
    ("chiropract", "health-medical"),
    ("optometr", "health-medical"),
    ("physiotherap", "health-medical"),
    ("medical", "health-medical"),
    ("veterin", "pets"),
    ("pet_", "pets"),
    ("pet_store", "pets"),
    ("animal", "pets"),
    ("lawyer", "professional"),
    ("attorney", "professional"),
    ("legal", "professional"),
    ("insurance", "professional"),
    ("real_estate", "professional"),
    ("finance", "professional"),
    ("financial", "professional"),
    ("accounting", "professional"),
    ("bank", "professional"),
    ("consultant", "professional"),
    ("hair", "beauty"),
    # ("barber", "beauty") lives in the eat-drink block above (it must precede
    # the bare "bar" token); a duplicate here was unreachable.
    ("nail", "beauty"),
    ("beauty", "beauty"),
    ("salon", "beauty"),
    ("spa", "beauty"),
    ("tanning", "beauty"),
    ("church", "civic-community"),
    ("synagogue", "civic-community"),
    ("mosque", "civic-community"),
    ("place_of_worship", "civic-community"),
    ("library", "civic-community"),
    ("non_profit", "civic-community"),
    ("local_government", "civic-community"),
    ("school", "kids-lessons"),
    ("university", "kids-lessons"),
    ("childcare", "kids-lessons"),
    # stay ("rv_park"/"campground" live earlier, above the bare "park" rule
    # that would otherwise swallow them — see the recreation block)
    ("vacation", "vacation-rentals"),
    ("resort", "hotels"),
    ("motel", "hotels"),
    ("hotel", "hotels"),
    ("lodging", "hotels"),
    # events / attractions
    ("museum", "attractions"),
    ("art_gallery", "attractions"),
    ("tourist", "attractions"),
    ("amusement", "attractions"),
    ("event_venue", "venues"),
)

# Legacy ``Provider.category`` value → subcategory slug. Coarser fallback used
# only when no specific Google type matched. Keys are the legacy slugs from
# ``CATEGORY_FILTERS`` / the seed data.
_LEGACY_TO_SUBCAT: dict[str, str] = {
    "food_drink": "restaurants",
    "food": "restaurants",
    "restaurant": "restaurants",
    "bakery": "cafes-coffee",
    "lake_recreation": "on-the-water",
    "boat_rental": "on-the-water",
    "boat_repair": "on-the-water",
    "recreation": "parks-beaches",
    # Net-new recreation verticals (USA Pickleball / PDGA loaders). The loaders
    # set Provider.subcategory explicitly; these keep the backfill pass
    # (scripts/backfill_subcategory.py) idempotent so it does not re-derive and
    # clobber the loader's value.
    "pickleball": "racquet-sports",
    "disc_golf": "disc-golf",
    "fitness_sports": "gyms",
    "fitness": "gyms",
    "childcare_education": "kids-lessons",
    "education": "kids-lessons",
    "edu": "kids-lessons",
    "retail": "specialty",
    "home_services": "home-services",
    "general_contractor": "home-services",
    "plumbing": "home-services",
    "auto": "auto",
    "health_medical": "health-medical",
    "professional_services": "professional",
    "real_estate": "professional",
    "insurance": "professional",
    "financial": "professional",
    "legal": "professional",
    "pets": "pets",
    "pet": "pets",
    "veterinary": "pets",
    "beauty_personal_care": "beauty",
    "religion_community": "civic-community",
    "lodging": "hotels",
    "entertainment_attractions": "attractions",
    "tourism": "attractions",
    "event_venue": "venues",
}


# ---------------------------------------------------------------------------
# WP-9 — canonical primary category (the 13). Single source of truth for the
# ``Provider.primary_category`` column and every public surface (Home, Explore,
# Map, Chat, "While you're here"). Deterministic, no LLM.
# ---------------------------------------------------------------------------
#
# Casey's locked decision: the canonical set is Home's categories (``CATEGORY_LABELS``
# in ``app/home/queries.py``) — 13 as of the Professional Services split. Explore's
# extra granularity (the ~31 subcategory slugs above, plus the legacy
# ``professional`` / ``beauty`` tiles) folds DOWN into these 13 as sub-chips, never
# as top-level categories.
#
# ``SUBCATEGORY_TO_PRIMARY`` is TOTAL over the live subcategory slugs in
# ``_SUBCATEGORIES`` — every subtype resolves to exactly one of the 13. The
# invariant test (tests/test_primary_category.py) asserts totality so a new
# subcategory can never silently drop off the canonical mapping.

# The 13 canonical primary-category slugs (mirrors home.queries.CATEGORY_LABELS
# keys). Kept here so this module — the taxonomy foundation — owns the slug set;
# home.queries' CATEGORY_LABELS supplies the human labels for the same slugs.
PRIMARY_CATEGORY_SLUGS: tuple[str, ...] = (
    "eat-drink",
    "on-the-water",
    "health-wellness-care",
    "home-property-services",
    "auto-rv-fuel",
    "shopping-essentials",
    "outdoors-parks-trails",
    "lodging-vacation-rentals",
    "pets",
    "classes-sports-recreation",
    "public-civic-resources",
    "professional-services",
    "events",
)

# subcategory slug -> one of the 13 canonical primaries. TOTAL over _SUBCATEGORIES.
#
# Notable folds (deterministic, defensible):
# * ``beauty`` folds into health-wellness-care (the canonical set has no standalone beauty
#   bucket; personal care reads as wellness). Mirrors home.queries'
#   beauty_personal_care handling under the wellness umbrella.
# * ``professional`` (legal/insurance/real-estate/financial/accounting) folds
#   into its own canonical ``professional-services`` primary — the 13th category.
#   It was previously folded into public-civic-resources (the 12 had no
#   professional bucket); the product decision split it out so resident-facing
#   "who do I call for X" pro services get a first-class home and the civic bucket
#   keeps only genuinely civic things (library/worship/government/community).
SUBCATEGORY_TO_PRIMARY: dict[str, str] = {
    # Eat & Drink
    "restaurants": "eat-drink",
    "bars-breweries": "eat-drink",
    "cafes-coffee": "eat-drink",
    "quick-bites": "eat-drink",
    # On the Water (incl. the marine trade split — boat sales/repair/supply)
    "on-the-water": "on-the-water",
    "marine-dealers": "on-the-water",
    "marine-repair": "on-the-water",
    "marine-supply": "on-the-water",
    # Outdoors, Parks & Trails
    "trails-offroad": "outdoors-parks-trails",
    "parks-beaches": "outdoors-parks-trails",
    "golf": "outdoors-parks-trails",
    "disc-golf": "outdoors-parks-trails",
    "biking": "outdoors-parks-trails",
    # Fitness, Sports & Classes
    "gyms": "classes-sports-recreation",
    "racquet-sports": "classes-sports-recreation",
    "martial-arts": "classes-sports-recreation",
    "studios": "classes-sports-recreation",
    "kids-lessons": "classes-sports-recreation",
    # Shopping, Grocery & Essentials
    "boutiques": "shopping-essentials",
    "home-goods": "shopping-essentials",
    "specialty": "shopping-essentials",
    "markets": "shopping-essentials",
    # Home & Property Services
    "home-services": "home-property-services",
    # Auto, RV & Fuel
    "auto": "auto-rv-fuel",
    # Health & Medical
    "health-medical": "health-wellness-care",
    "beauty": "health-wellness-care",
    # Professional Services (legal/insurance/real-estate/financial/accounting).
    "professional": "professional-services",
    # Public & Civic Resources (genuinely civic things only — see note above)
    "civic-community": "public-civic-resources",
    # Pets
    "pets": "pets",
    # Lodging & Vacation Rentals
    "hotels": "lodging-vacation-rentals",
    "vacation-rentals": "lodging-vacation-rentals",
    "rv-parks": "lodging-vacation-rentals",
    # Events (provider-side venues; calendar events are a separate feed)
    "attractions": "events",
    "venues": "events",
    # Storage (Services bucket) -> Home & Property Services (it's a property
    # service, and the 12 have no standalone storage bucket).
    "storage": "home-property-services",
}

# Legacy ``Provider.category`` string -> canonical primary, used ONLY when no
# subcategory has been derived (the NULL-subcategory fallback). Coarser than the
# subcategory map; mirrors LEGACY_PROVIDER_CATEGORY_LABELS' intent so a row with
# only a legacy category still lands on the right primary.
LEGACY_CATEGORY_TO_PRIMARY: dict[str, str] = {
    "food_drink": "eat-drink",
    "food": "eat-drink",
    "restaurant": "eat-drink",
    "bakery": "eat-drink",
    "lake_recreation": "on-the-water",
    "boat_rental": "on-the-water",
    "boat_repair": "on-the-water",
    # These direct folds must agree with the _LEGACY_TO_SUBCAT →
    # SUBCATEGORY_TO_PRIMARY derivation (which is what actually places a row on
    # a listing): a divergent entry makes an un-backfilled (NULL-primary) row
    # COUNT under one department while LISTING under another — the
    # count-vs-listing drift WP-12 exists to prevent. fitness_sports/fitness
    # used to fold to health-wellness-care while gyms (their derived
    # subcategory) lands on classes-sports-recreation.
    # tests/test_audit_categories_fixes.py asserts the two paths agree map-wide.
    # KNOWN EXCEPTION: "recreation" folds here to classes-sports-recreation
    # (CATEGORY_FILTERS + /api/map_data expect that) while its derived
    # subcategory (parks-beaches) lands on outdoors-parks-trails — the legacy
    # bucket genuinely straddles both departments and only a per-row recat can
    # split it; documented in the test's exception list.
    "recreation": "classes-sports-recreation",
    "fitness_sports": "classes-sports-recreation",
    "fitness": "classes-sports-recreation",
    "childcare_education": "classes-sports-recreation",
    "education": "classes-sports-recreation",
    "edu": "classes-sports-recreation",
    "retail": "shopping-essentials",
    "home_services": "home-property-services",
    "general_contractor": "home-property-services",
    "plumbing": "home-property-services",
    "services": "home-property-services",
    "auto": "auto-rv-fuel",
    "health_medical": "health-wellness-care",
    "professional_services": "professional-services",
    "real_estate": "professional-services",
    "insurance": "professional-services",
    "financial": "professional-services",
    "legal": "professional-services",
    "beauty_personal_care": "health-wellness-care",
    "pets": "pets",
    "pet": "pets",
    "veterinary": "pets",
    "religion_community": "public-civic-resources",
    "lodging": "lodging-vacation-rentals",
    "entertainment_attractions": "events",
    "tourism": "events",
    "event_venue": "events",
    "events": "events",
    "music": "events",
}


def primary_for_subcategory(subcategory: str | None) -> str | None:
    """Canonical primary slug for a subcategory slug, or ``None`` if unknown."""
    if not subcategory:
        return None
    return SUBCATEGORY_TO_PRIMARY.get(subcategory.strip().lower())


def derive_primary_category(
    *,
    category: str | None,
    subcategory: str | None = None,
    name: str | None = None,
    google_primary_category: str | None = None,
    google_categories: Any = None,
    attributes: Any = None,
) -> str | None:
    """Best canonical primary-category slug (one of the 13), or ``None``.

    Pure (no DB / ORM) so it backfills offline and runs on ingest. Precedence:

    1. The provider's derived ``subcategory`` (the strong Google-derived signal)
       mapped through ``SUBCATEGORY_TO_PRIMARY``.
    2. If no subcategory was stored, derive one from Google types / legacy
       category via :func:`derive_subcategory`, then map it.
    3. Legacy ``Provider.category`` mapped through ``LEGACY_CATEGORY_TO_PRIMARY``.

    Returns ``None`` only when nothing matches — never guesses a default.
    """
    sub = (subcategory or "").strip().lower() or None
    if sub is None:
        sub = derive_subcategory(
            category=category,
            name=name,
            google_primary_category=google_primary_category,
            google_categories=google_categories,
            attributes=attributes,
        )
    if sub:
        primary = SUBCATEGORY_TO_PRIMARY.get(sub)
        if primary:
            return primary
    if category:
        key = category.strip().lower()
        if key in LEGACY_CATEGORY_TO_PRIMARY:
            return LEGACY_CATEGORY_TO_PRIMARY[key]
    return None


def _iter_type_tokens(
    primary: str | None, categories: Any, sub_trades: Iterable[str] | None
) -> Iterable[str]:
    # Signal-priority order — now decisive in _subcat_from_types: the specific
    # primary type first, then curated sub_trades, then the generic-laden
    # google_categories array.
    if primary:
        yield str(primary).lower()
    if sub_trades:
        for s in sub_trades:
            yield str(s).lower()
    if isinstance(categories, list):
        for c in categories:
            yield str(c).lower()


# Generic catch-all tokens that only count when a type IS the token, not when it
# merely contains it. Without this, the bare "store" rule swallows every
# specific *_store type that appears later in the table ("auto_parts_store" ->
# specialty instead of auto, "pet_store" -> specialty instead of pets; prod bug
# surfaced by the 2026-06-04 category patrol: 365 flags, mostly this).
_EXACT_ONLY_NEEDLES = frozenset({"store"})


def _match_subcat(tok: str) -> str | None:
    """First _TYPE_TO_SUBCAT hit for a single type token, or None."""
    for needle, slug in _TYPE_TO_SUBCAT:
        if needle in _EXACT_ONLY_NEEDLES:
            if tok == needle:
                return slug
        elif needle in tok:
            return slug
    return None


def _subcat_from_types(
    primary: str | None, categories: Any, sub_trades: Iterable[str] | None
) -> str | None:
    """Token tiers are decisive: the specific ``google_primary_category`` is
    consulted against the whole rule table before curated sub_trades, and both
    before the noisy ``google_categories`` array. Previously the RULE order was
    the outer loop, so a generic early rule matched against an array token could
    outvote a specific later rule matching the primary type ("car_dealer" +
    ["store", ...] filed as specialty/shopping instead of auto; 2026-06-04
    category patrol flagged 105 such rows).
    """
    primary_lower = str(primary).lower() if primary else None
    for tok in _iter_type_tokens(primary, categories, sub_trades):
        hit = _match_subcat(tok)
        if hit:
            return hit
        # A *_store primary type with no specific rule (convenience_store,
        # jewelry_store, toy_store, ...) is still definitively a shop — file it
        # as specialty rather than letting incidental array tokens (atm,
        # finance, tourist_attraction) drag it into another bucket.
        if tok == primary_lower and tok.endswith("_store"):
            return "specialty"
    return None


# Marine trade routing from the business NAME (2026-06-13 audit). Boat
# businesses carry generic Google types (``service``/``store``/``supplier``), so
# the type-token tiers file them as ``specialty`` / generic ``on-the-water`` and
# a re-derive would clobber the marine-* leaf split. When a NAME is available it
# is the decisive signal: an anchor token (boat/marine/watercraft/nautical) plus
# a trade qualifier pins the row to dealers / repair / supply. Watersports
# rentals (jet ski / kayak) are intentionally NOT matched here — they stay
# on-the-water. Returns one of the three marine subcats or ``None``.
_MARINE_ANCHOR = re.compile(r"\b(boats?|marine|watercraft|nautical)\b", re.I)
_MARINE_REPAIR = re.compile(
    r"\b(service|repair|mechanic|performance|fiberglass|gel ?coat|gelcraft|"
    r"machine|engines?|rigging|restoration|customs?|body shop|speed)\b",
    re.I,
)
_MARINE_SUPPLY = re.compile(r"\b(supply|supplies|parts|store)\b|west marine", re.I)
_MARINE_DEALER = re.compile(r"\bboats\b|\b(sales|dealer|brokers?|power boats|custom boats)\b", re.I)


def _marine_subcat_from_name(name: str | None) -> str | None:
    if not name:
        return None
    n = name.lower()
    if not _MARINE_ANCHOR.search(n):
        return None
    # Order: supply (store/parts) and dealer (sales/boats) before the broad
    # repair qualifier, so "Marine Sales & Service" reads as a dealer.
    if _MARINE_SUPPLY.search(n):
        return "marine-supply"
    if _MARINE_DEALER.search(n):
        return "marine-dealers"
    if _MARINE_REPAIR.search(n):
        return "marine-repair"
    return None


# Martial-arts routing from the business NAME (2026-06-15 coverage audit). Dojos
# carry generic Google types (gym / school / point_of_interest), so the type
# tiers file them as ``gyms`` / ``kids-lessons`` and the ``martial-arts``
# subcategory page renders empty even though the rows exist. A distinctive
# discipline token in the NAME is decisive. Generic words ("academy", "combat",
# "fitness", "club") are intentionally NOT matched — too many false positives
# (dance academies, etc.); those are handled by manual review.
_MARTIAL_ARTS_NAME = re.compile(
    r"martial arts|mixed martial|jiu[\s-]?jitsu|\bbjj\b|\bkarate\b|"
    r"tae ?kwon ?do|taekwondo|\bkempo\b|\bkenpo\b|krav maga|muay thai|"
    r"kickbox|kick boxing|\bjudo\b|\baikido\b|kung ?fu|black belt|\bdojo\b|"
    r"self[\s-]?defense",
    re.I,
)


def _martial_subcat_from_name(name: str | None) -> str | None:
    if name and _MARTIAL_ARTS_NAME.search(name):
        return "martial-arts"
    return None


def is_martial_arts_name(name: str | None) -> bool:
    """True when a business/venue NAME carries a martial-arts discipline token
    (jiu-jitsu, bjj, karate, taekwondo, kempo, krav maga, muay thai, judo,
    aikido, kung fu, black belt, dojo, self-defense, …).

    Reused by the events page (:func:`app.home.events_views._class_subgroup`) to
    file every class held at a martial-arts venue under the Martial Arts
    subsection — so the catalog's martial-arts studios are covered automatically
    as they're added, without a hand-maintained venue list."""
    return bool(name) and bool(_MARTIAL_ARTS_NAME.search(name))


# Vacation-rental routing from the business NAME (2026-06-15 coverage audit).
# These carry Google type ``lodging`` / ``real_estate_agency``, so the type
# tiers file them as ``hotels`` and the ``vacation-rentals`` page renders empty.
# A "vacation rental/home/stay" signal in the NAME is decisive. Bare "property
# management" is intentionally excluded (ambiguous: long-term / commercial / HOA).
_VACATION_RENTAL_NAME = re.compile(
    r"vacation rental|vacation home|vacation stay|\bvrbo\b|short[\s-]?term rental",
    re.I,
)


def _vacation_subcat_from_name(name: str | None) -> str | None:
    if name and _VACATION_RENTAL_NAME.search(name):
        return "vacation-rentals"
    return None


def derive_subcategory(
    *,
    category: str | None,
    name: str | None = None,
    google_primary_category: str | None = None,
    google_categories: Any = None,
    attributes: Any = None,
) -> str | None:
    """Best subcategory slug for a provider, or ``None`` when nothing matches.

    Pure (no DB / ORM) so it backfills offline and runs on ingest. Precedence:
    decisive NAME signal (marine trade) → specific Google type → legacy category
    bucket. ``sub_trades`` (curated) participate at the Google-type tier. ``name``
    is optional and backward-compatible: omit it and behaviour is unchanged.
    """
    marine = _marine_subcat_from_name(name)
    if marine:
        return marine

    martial = _martial_subcat_from_name(name)
    if martial:
        return martial

    vacation = _vacation_subcat_from_name(name)
    if vacation:
        return vacation

    sub_trades: list[str] | None = None
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except (ValueError, TypeError):
            attributes = None
    if isinstance(attributes, dict):
        raw = attributes.get("sub_trades")
        if isinstance(raw, list):
            sub_trades = [str(s) for s in raw if s]

    if isinstance(google_categories, str):
        try:
            google_categories = json.loads(google_categories)
        except (ValueError, TypeError):
            google_categories = None

    hit = _subcat_from_types(google_primary_category, google_categories, sub_trades)
    if hit:
        return hit

    if category:
        key = category.strip().lower()
        if key in _LEGACY_TO_SUBCAT:
            return _LEGACY_TO_SUBCAT[key]
    return None


# ---------------------------------------------------------------------------
# Cuisine (C-2) — a second-level facet under Food & Drink › Restaurants.
# ---------------------------------------------------------------------------
#
# Derived deterministically from Google types (``mexican_restaurant`` → Mexican).
# Order matters: specific ethnic/style tokens are checked before the broad
# ``american`` / ``diner`` fallbacks so a place tagged both lands on the specific
# one. ``pizza`` precedes ``italian`` so pizzerias read as Pizza. Returns ``None``
# when no cuisine token matches — the chip simply isn't shown for that card.

# (slug, label, match tokens) — tokens matched as substrings of lowercased types.
_CUISINES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("mexican", "Mexican", ("mexican", "taco", "taqueria", "burrito")),
    ("pizza", "Pizza", ("pizza", "pizzeria")),
    ("italian", "Italian", ("italian",)),
    ("chinese", "Chinese", ("chinese",)),
    ("japanese", "Japanese", ("japanese", "sushi", "ramen")),
    ("thai", "Thai", ("thai",)),
    ("indian", "Indian", ("indian",)),
    ("mediterranean", "Mediterranean", ("mediterranean", "greek")),
    ("bbq", "BBQ", ("barbecue", "barbeque", "bbq")),
    ("seafood", "Seafood", ("seafood",)),
    ("steakhouse", "Steakhouse", ("steak",)),
    ("burgers", "Burgers", ("burger", "hamburger")),
    ("sandwiches", "Sandwiches", ("sandwich", "deli", "_sub_", "submarine")),
    ("breakfast", "Breakfast", ("breakfast", "brunch", "pancake")),
    ("diner", "Diner", ("diner",)),
    # WS9a enum additions (Casey, 2026-07-08): specific cuisines that show up in
    # Google types with no home in the enum. Each currently has a single Havasu
    # member, so the >= _CUISINE_CHIP_MIN (2) chip rule keeps them OUT of the facet
    # row — the enum HOLDS the value (search / data), the UI stays uncluttered.
    # KFC maps to ``fried_chicken`` because the enum has no generic "fast food"
    # home. Kept before the generic ``american`` so a specific type wins.
    ("korean", "Korean", ("korean",)),
    ("cuban", "Cuban", ("cuban",)),
    ("fried_chicken", "Fried Chicken", ("chicken_restaurant", "fried_chicken")),
    ("american", "American", ("american",)),
)

_CUISINE_LABELS: dict[str, str] = {slug: label for slug, label, _ in _CUISINES}
_CUISINE_ORDER: list[str] = [slug for slug, _, _ in _CUISINES]


def cuisine_label(slug: str | None) -> str | None:
    return _CUISINE_LABELS.get((slug or "").strip().lower()) if slug else None


def cuisine_slugs_in_order() -> list[str]:
    """Canonical display order for cuisine chips."""
    return list(_CUISINE_ORDER)


def derive_cuisine(
    google_primary_category: str | None = None,
    google_categories: Any = None,
) -> str | None:
    """Best cuisine slug for a restaurant from its Google types, or ``None``.

    Pure (no DB). Checks the primary type first, then secondary types; first
    matching cuisine in ``_CUISINES`` order wins.
    """
    if isinstance(google_categories, str):
        try:
            google_categories = json.loads(google_categories)
        except (ValueError, TypeError):
            google_categories = None
    tokens = list(_iter_type_tokens(google_primary_category, google_categories, None))
    for slug, _label, needles in _CUISINES:
        for needle in needles:
            for tok in tokens:
                if needle in tok:
                    return slug
    return None


def effective_cuisine(
    attributes: Any = None,
    google_primary_category: str | None = None,
    google_categories: Any = None,
) -> str | None:
    """Cuisine for a restaurant: curated override first, else derived.

    The WS9a backfill writes an operator-approved cuisine to
    ``Provider.attributes['cuisine']`` (a valid enum slug); it WINS over the
    Google-types :func:`derive_cuisine` so a name-only classification ("Filiberto's
    Mexican Food", whose Google types carry no cuisine token) still surfaces on the
    facet. A provider with no curated value (or an unknown/invalid one) falls back
    to the derivation — so this is a no-op until the gated backfill applies. Pure,
    never raises.
    """
    if isinstance(attributes, dict):
        curated = str(attributes.get("cuisine") or "").strip().lower()
        if curated in _CUISINE_LABELS:
            return curated
    return derive_cuisine(google_primary_category, google_categories)


# --- Free-text cuisine intent (search routing) -----------------------------
#
# A plain cuisine/dish search ("mexican food", "tacos", "sushi", "pizza") must
# reach the Eat & Drink listing filtered to that cuisine — NOT the events
# calendar (the old ``_TYPE_WORDS`` "events" bucket matched bare "food"/"taco"
# and swallowed cuisine queries into ``/calendar``). This resolver maps such a
# query to its cuisine slug so the router can send it to
# ``/lake-havasu/{cuisine}``.
#
# Deliberately conservative: it matches only an exact "<cuisine> [food/dining
# tail]" phrase (after one leading qualifier is stripped) and returns ``None``
# the moment the query carries an event/temporal signal, so a genuine calendar
# ask ("taco festival", "food truck night") is never captured.

#: Generic food/dining tails that may follow a cuisine word in a search.
#: The empty tail lets a bare cuisine/dish word ("tacos", "sushi") match.
_CUISINE_TAILS: tuple[str, ...] = (
    "", "food", "foods", "restaurant", "restaurants", "cuisine",
    "place", "places", "spot", "spots", "joint", "joints",
    "eatery", "eateries", "takeout", "delivery",
)

#: One leading qualifier we tolerate ("good mexican food", "authentic tacos").
_CUISINE_LEAD_RE = re.compile(
    r"^(?:the\s+)?(?:best|good|great|authentic|real|local|top|nearby|some|a|an)\s+"
)

#: Event/discovery words that make a query a calendar ask, not a restaurant
#: search ("taco festival", "food truck night", "cooking class"). Their presence
#: forces ``cuisine_query_slug`` to return ``None`` so the calendar keeps them.
_CUISINE_EVENT_EXCLUDE_RE = re.compile(
    r"\b(festival|festivals|fest|event|events|fair|market|truck|trucks|"
    r"night|crawl|tasting|tastings|class|classes|cooking|competition|contest|"
    r"tonight|tomorrow|weekend|week|today)\b"
)


def _build_cuisine_phrase_map() -> dict[str, str]:
    """``{normalized phrase: cuisine slug}`` for exact cuisine-query lookup.

    Built from every cuisine's label + synonym needles crossed with the food
    tails (and simple plurals so "taco" → "tacos", "burger" → "burgers"). First
    cuisine in ``_CUISINES`` order wins a shared phrase.
    """
    out: dict[str, str] = {}
    for slug, label, needles in _CUISINES:
        bases: set[str] = {label.lower()}
        for n in needles:
            if n.startswith("_"):  # placeholder tokens like "_sub_"
                continue
            bases.add(n)
            bases.add(f"{n}s")  # taco → tacos, burger → burgers, burrito → burritos
        for base in bases:
            for tail in _CUISINE_TAILS:
                phrase = f"{base} {tail}".strip()
                out.setdefault(phrase, slug)
    return out


_CUISINE_PHRASE_MAP: dict[str, str] = _build_cuisine_phrase_map()


def cuisine_query_slug(q: str | None) -> str | None:
    """Cuisine slug a plain restaurant/dish search maps to, or ``None``.

    Pure (no DB). Returns ``None`` for any query carrying an event/temporal
    signal, so a genuine calendar ask ("taco festival") is never treated as a
    restaurant search. The caller still gates the resulting cuisine page on its
    publish threshold before redirecting.
    """
    s = (q or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s or _CUISINE_EVENT_EXCLUDE_RE.search(s):
        return None
    s = _CUISINE_LEAD_RE.sub("", s).strip()
    return _CUISINE_PHRASE_MAP.get(s)
