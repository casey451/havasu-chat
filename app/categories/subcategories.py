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
    Subcategory("on-the-water", "On the Water", "recreation-outdoors", "Marinas, launches, rentals."),
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
    Subcategory("auto", "Auto", "services", "Repair, body, tires, RV & boat."),
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


def subcategories_for_category_route(route_slug: str | None) -> list[Subcategory]:
    """Chip set for a plural category page — empty when the route isn't a bucket
    destination (tile routes like ``beauty-care`` show no second level)."""
    bucket_id = bucket_for_category_route(route_slug)
    return subcategories_for_bucket(bucket_id) if bucket_id else []


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
    ("park", "parks-beaches"),
    ("campground", "parks-beaches"),
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
    ("auto", "auto"),
    ("tire", "auto"),
    ("car_wash", "auto"),
    ("car_dealer", "auto"),
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
    ("barber", "beauty"),
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
    # stay
    ("vacation", "vacation-rentals"),
    ("rv_park", "rv-parks"),
    ("campground", "rv-parks"),
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


def _iter_type_tokens(
    primary: str | None, categories: Any, sub_trades: Iterable[str] | None
) -> Iterable[str]:
    if primary:
        yield str(primary).lower()
    if isinstance(categories, list):
        for c in categories:
            yield str(c).lower()
    if sub_trades:
        for s in sub_trades:
            yield str(s).lower()


def _subcat_from_types(
    primary: str | None, categories: Any, sub_trades: Iterable[str] | None
) -> str | None:
    tokens = list(_iter_type_tokens(primary, categories, sub_trades))
    for needle, slug in _TYPE_TO_SUBCAT:
        for tok in tokens:
            if needle in tok:
                return slug
    return None


def derive_subcategory(
    *,
    category: str | None,
    google_primary_category: str | None = None,
    google_categories: Any = None,
    attributes: Any = None,
) -> str | None:
    """Best subcategory slug for a provider, or ``None`` when nothing matches.

    Pure (no DB / ORM) so it backfills offline and runs on ingest. Precedence:
    specific Google type → legacy category bucket. ``sub_trades`` (curated)
    participate at the Google-type tier.
    """
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
