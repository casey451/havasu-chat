"""Chat-query → leaf-page routing (Workstream B.3).

Conservative "exact category match" (Casey's confirmed threshold): a /chat query
routes straight to a leaf page ONLY when, after stripping locality/filler, it is
essentially just the category noun — "plumbers", "boat rentals", "med spas".
Anything descriptive ("best plumber for a slab leak", "is there a vet open now")
falls through and stays conversational.

The match is a single in-memory dict lookup (zero DB cost for non-matches); a
candidate only then hits the DB to confirm the leaf exists and clears the
≥3-provider gate. Leaves with no synonym entry simply never auto-route — safe
by omission.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.categories import leaf_pages
from app.chat.normalizer import spell_correct

# Normalized colloquial term → leaf slug. Keys are the output of ``_normalize``
# (lowercase, ``&``→``and``, punctuation dropped, locality/filler stripped).
# Singular + plural + common synonyms are listed explicitly — no fragile
# stemming. Only confident, unambiguous navigational terms belong here.
_QUERY_TO_LEAF: dict[str, str] = {
    # Eat & Drink
    "restaurants": "restaurants",
    "restaurant": "restaurants",
    "places to eat": "restaurants",
    "where to eat": "restaurants",
    "bars": "bars-and-breweries",
    "breweries": "bars-and-breweries",
    "bars and breweries": "bars-and-breweries",
    "bakeries": "bakeries-and-desserts",
    "bakery": "bakeries-and-desserts",
    "coffee": "caf-s-and-coffee",
    "coffee shops": "caf-s-and-coffee",
    "cafes": "caf-s-and-coffee",
    "food trucks": "food-trucks-and-catering",
    "catering": "food-trucks-and-catering",
    # On the Water
    "boat rentals": "boat-and-watercraft-rentals",
    "boat rental": "boat-and-watercraft-rentals",
    "watercraft rentals": "boat-and-watercraft-rentals",
    "jet ski rentals": "jet-ski-and-watersports",
    "jet skis": "jet-ski-and-watersports",
    "kayak rentals": "kayak-and-paddle",
    "kayaks": "kayak-and-paddle",
    "paddleboards": "kayak-and-paddle",
    "boat tours": "boat-tours-and-charters",
    "fishing charters": "fishing-charters-and-guides",
    "beaches": "beaches-and-swim-areas",
    "marinas": "marinas-and-launch-ramps",
    # Outdoors & Recreation
    "parks": "parks-and-playgrounds",
    "golf courses": "golf-courses",
    "golf": "golf-courses",
    "hiking trails": "hiking-trails",
    "hiking": "hiking-trails",
    "disc golf": "disc-golf",
    "dog parks": "dog-parks",
    # Things to Do
    "tours": "tours-and-sightseeing",
    "museums": "museums-and-galleries",
    "theaters": "theaters-and-cinema",
    "movie theaters": "theaters-and-cinema",
    "cinema": "theaters-and-cinema",
    # Health & Medical
    "doctors": "primary-care",
    "primary care": "primary-care",
    "dentists": "dentists-and-orthodontists",
    "dentist": "dentists-and-orthodontists",
    "orthodontists": "dentists-and-orthodontists",
    "pharmacies": "pharmacies",
    "pharmacy": "pharmacies",
    "chiropractors": "chiropractic",
    "chiropractor": "chiropractic",
    "physical therapy": "physical-therapy",
    "eye care": "eye-care",
    "optometrists": "eye-care",
    # Beauty & Personal Care
    "hair salons": "hair-salons-and-barbers",
    "hair salon": "hair-salons-and-barbers",
    "barbers": "hair-salons-and-barbers",
    "barber": "hair-salons-and-barbers",
    "salons": "hair-salons-and-barbers",
    "spas": "day-spas-and-massage",
    "massage": "day-spas-and-massage",
    "day spas": "day-spas-and-massage",
    "nail salons": "nail-salons",
    "nails": "nail-salons",
    "tattoo": "tattoo-and-piercing",
    "tattoo shops": "tattoo-and-piercing",
    "tanning": "tanning",
    "med spas": "med-spas-and-aesthetics",
    "med spa": "med-spas-and-aesthetics",
    "medical spas": "med-spas-and-aesthetics",
    # Fitness & Wellness
    "gyms": "gyms-and-fitness-centers",
    "gym": "gyms-and-fitness-centers",
    "fitness centers": "gyms-and-fitness-centers",
    "yoga": "yoga-and-pilates",
    "pilates": "yoga-and-pilates",
    "dance studios": "dance-studios",
    # Pets
    "dog grooming": "grooming",
    "pet grooming": "grooming",
    "groomers": "grooming",
    "vets": "veterinarians",
    "veterinarians": "veterinarians",
    "vet": "veterinarians",
    "pet stores": "pet-stores-and-supplies",
    "dog training": "training",
    # Home & Property
    "general contractors": "general-contractors",
    "contractors": "general-contractors",
    "self storage": "self-storage",
    "storage units": "self-storage",
    "electricians": "electrical",
    "electrician": "electrical",
    "cleaning services": "cleaning",
    "house cleaning": "cleaning",
    "maids": "cleaning",
    "plumbers": "plumbing",
    "plumber": "plumbing",
    "plumbing": "plumbing",
    "roofers": "roofing",
    "roofer": "roofing",
    "roofing": "roofing",
    "pest control": "pest-control",
    "exterminators": "pest-control",
    "solar": "solar",
    "solar installers": "solar",
    "landscapers": "landscaping-and-lawn",
    "landscaping": "landscaping-and-lawn",
    "lawn care": "landscaping-and-lawn",
    "pool service": "pools-and-spas",
    "pool cleaning": "pools-and-spas",
    "hvac": "hvac",
    "air conditioning": "hvac",
    "ac repair": "hvac",
    "movers": "movers",
    "moving companies": "movers",
    # Auto, RV & Marine
    "auto repair": "auto-repair",
    "mechanics": "auto-repair",
    "car repair": "auto-repair",
    "gas stations": "gas-stations",
    "car dealerships": "car-dealerships",
    "auto parts": "auto-parts",
    "car wash": "car-wash",
    "car washes": "car-wash",
    "towing": "towing-and-roadside",
    "tow trucks": "towing-and-roadside",
    "car rentals": "car-rental",
    "tires": "tires",
    "tire shops": "tires",
    # Shopping & Retail
    "clothing stores": "clothing-and-apparel",
    "hardware stores": "hardware-and-home-improvement",
    "furniture stores": "furniture-and-mattress",
    "sporting goods": "sporting-goods",
    "grocery stores": "grocery-and-markets",
    "groceries": "grocery-and-markets",
    "jewelry stores": "jewelry",
    "jewelers": "jewelry",
    "thrift stores": "thrift-and-consignment",
    "florists": "florists",
    "flower shops": "florists",
    # Professional & Financial
    "financial advisors": "financial-advisors",
    "financial advisor": "financial-advisors",
    "real estate": "real-estate",
    "realtors": "real-estate",
    "real estate agents": "real-estate",
    "insurance": "insurance",
    "insurance agents": "insurance",
    "attorneys": "attorneys",
    "lawyers": "attorneys",
    "accountants": "accountants-and-tax",
    "tax preparers": "accountants-and-tax",
    "banks": "banks-and-credit-unions",
    "credit unions": "banks-and-credit-unions",
    "photographers": "photographers",
    # Family & Education
    "preschools": "preschools-and-childcare",
    "childcare": "preschools-and-childcare",
    "daycare": "preschools-and-childcare",
    "schools": "k-12-schools",
    # Community & Civic
    "churches": "places-of-worship",
    "libraries": "libraries",
    # Lodging
    "hotels": "hotels-and-motels",
    "hotel": "hotels-and-motels",
    "motels": "hotels-and-motels",
    "lodging": "hotels-and-motels",
    "places to stay": "hotels-and-motels",
    "rv parks": "rv-parks-and-campgrounds",
    "campgrounds": "rv-parks-and-campgrounds",
}

# Locality + filler stripped before lookup. Order matters (longest first).
_FILLER_PHRASES: tuple[str, ...] = (
    "lake havasu city",
    "lake havasu",
    "in havasu",
    "near me",
    "around here",
    "open now",
    "havasu",
    "arizona",
    "az",
)
_LEADING = re.compile(
    r"^(find|show me|show|the best|best|top|good|a|an|some|any)\s+"
)


def _normalize(q: str) -> str:
    s = (q or "").strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)  # drop apostrophes/punctuation
    s = re.sub(r"\s+", " ", s).strip()
    # Shared misspelling tolerance: "plummbers" → "plumbers" before the dict
    # lookup, so /chat navigational routing inherits the same correction layer
    # the conversational tiers get via normalizer.normalize().
    s = spell_correct(s)
    for phrase in _FILLER_PHRASES:
        s = re.sub(rf"\b{re.escape(phrase)}\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Strip one leading qualifier ("best plumbers" -> "plumbers").
    prev = None
    while prev != s:
        prev = s
        s = _LEADING.sub("", s).strip()
    # Drop a trailing "in"/"near" left dangling by locality removal.
    s = re.sub(r"\s+(in|near|at|around)$", "", s).strip()
    return s


def match_leaf_query(db: Session, q: str | None) -> leaf_pages.Leaf | None:
    """A gate-clearing leaf the query maps to EXACTLY, or ``None``.

    Conservative: the normalized query must equal a known navigational term.
    The candidate leaf must exist and clear the ≥3-provider gate, else ``None``
    (so the query stays conversational).
    """
    norm = _normalize(q or "")
    if not norm:
        return None
    slug = _QUERY_TO_LEAF.get(norm)
    if slug is None:
        return None
    leaf = leaf_pages.resolve_leaf_by_slug(db, slug)
    if leaf is None:
        return None
    if leaf_pages.leaf_renderable_count(db, leaf) < leaf_pages.LEAF_PAGE_MIN_PROVIDERS:
        return None
    return leaf
