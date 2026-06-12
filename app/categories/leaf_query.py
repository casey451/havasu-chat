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

2026-06-11 (intent-efficiency pass): widened with the coverage-audit trades.
Entries pointing at leaves that do not exist yet are harmless by construction
(``resolve_leaf_by_slug`` returns ``None`` → conversational fall-through) and
self-activate the moment the taxonomy rebuild seeds the leaf. Those slugs are
tracked in ``PENDING_LEAF_SLUGS`` so a sync test can flag drift if the rebuild
picks different slug names.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.categories import leaf_pages
from app.chat.normalizer import spell_correct

# Leaf slugs referenced below that are expected from the taxonomy rebuild
# (HAVA_AUDIT_AND_TAXONOMY_REBUILD.md §3) but not yet in the live seed. A
# dict entry pointing at one of these is a deliberate no-op until the leaf
# ships. tests/test_leaf_query_additions.py asserts every _QUERY_TO_LEAF slug
# is either live in docs/proposals/taxonomy-seed.json or listed here — so a
# rebuild that picks a different slug name fails CI instead of leaving dead
# entries.
PENDING_LEAF_SLUGS: frozenset[str] = frozenset(
    {
        "hearing-and-audiology",
        "medical-specialists-and-imaging",
        "golf-carts",
        "auto-glass",
        "window-tint-and-wraps",
        "trailer-sales-and-repair",
        "property-management",
        "laundry-and-dry-cleaning",
        "funeral-cremation-and-cemeteries",
        "junk-removal-and-hauling",
        "pressure-washing-and-exterior-cleaning",
        "mobile-home-services",
        "shade-screens-and-patio-covers",
        "pet-waste-removal",
        "firearms-and-shooting-sports",
    }
)

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
    "coffee": "cafes-and-coffee",
    "coffee shops": "cafes-and-coffee",
    "cafes": "cafes-and-coffee",
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
    # 2026-06-11: off-road is a Havasu-signature ask with a live leaf.
    "off roading": "off-road-and-ohv",
    "off road trails": "off-road-and-ohv",
    "ohv": "off-road-and-ohv",
    "utv trails": "off-road-and-ohv",
    "atv trails": "off-road-and-ohv",
    # Things to Do
    "tours": "tours-and-sightseeing",
    "museums": "museums-and-galleries",
    "theaters": "theaters-and-cinema",
    "movie theaters": "theaters-and-cinema",
    "cinema": "theaters-and-cinema",
    # hunt 2026-06-10 §2: real-miss 3x HIGH; Havasu Lanes primary leaf verified
    # against entity_categories (category id 56 = family-fun-and-arcades)
    "bowling": "family-fun-and-arcades",
    "bowling alley": "family-fun-and-arcades",
    "bowling alleys": "family-fun-and-arcades",
    # 2026-06-11
    "arcades": "family-fun-and-arcades",
    "arcade": "family-fun-and-arcades",
    "casinos": "casinos-and-gaming",
    "casino": "casinos-and-gaming",
    "landmarks": "landmarks-and-sights",
    "sightseeing": "tours-and-sightseeing",
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
    # hunt 2026-06-10 §2: sweep n=8, no route
    "physical therapist": "physical-therapy",
    "physiotherapist": "physical-therapy",
    "physio": "physical-therapy",
    "eye care": "eye-care",
    "optometrists": "eye-care",
    # 2026-06-11: existing leaves with no navigational entry (sweep gaps).
    "urgent care": "urgent-care-and-er",
    "walk in clinic": "urgent-care-and-er",
    "walk in clinics": "urgent-care-and-er",
    "dermatologist": "dermatology-and-skin",
    "dermatologists": "dermatology-and-skin",
    "counselors": "mental-and-behavioral-health",
    "therapists": "mental-and-behavioral-health",
    "mental health": "mental-and-behavioral-health",
    "assisted living": "senior-care-and-assisted-living",
    "senior care": "senior-care-and-assisted-living",
    "retirement homes": "senior-care-and-assisted-living",
    "nursing homes": "senior-care-and-assisted-living",
    # 2026-06-11: taxonomy-rebuild leaves (PENDING — self-activate at seed).
    "hearing aids": "hearing-and-audiology",
    "audiologists": "hearing-and-audiology",
    "audiologist": "hearing-and-audiology",
    "hearing centers": "hearing-and-audiology",
    # Beauty & Personal Care
    "hair salons": "hair-salons-and-barbers",
    "hair salon": "hair-salons-and-barbers",
    "barbers": "hair-salons-and-barbers",
    "barber": "hair-salons-and-barbers",
    "salons": "hair-salons-and-barbers",
    # hunt 2026-06-10 §2: sweep n=50, no route
    "salon": "hair-salons-and-barbers",
    "beauty salon": "hair-salons-and-barbers",
    "beauty salons": "hair-salons-and-barbers",
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
    # 2026-06-11
    "martial arts": "martial-arts",
    "karate": "martial-arts",
    "personal trainers": "personal-training",
    "personal trainer": "personal-training",
    "nutritionists": "nutrition-and-wellness",
    # Pets
    "dog grooming": "grooming",
    "pet grooming": "grooming",
    "groomers": "grooming",
    "groomer": "grooming",
    "dog groomer": "grooming",
    "dog groomers": "grooming",
    "pet groomer": "grooming",
    "pet groomers": "grooming",
    "vets": "veterinarians",
    "veterinarians": "veterinarians",
    "vet": "veterinarians",
    "veterinarian": "veterinarians",
    "pet stores": "pet-stores-and-supplies",
    "pet store": "pet-stores-and-supplies",
    "dog training": "training",
    "dog trainer": "training",
    "dog trainers": "training",
    # 2026-06-11
    "pet sitters": "pet-sitting",
    "pet sitting": "pet-sitting",
    "dog sitters": "pet-sitting",
    "dog boarding": "boarding-and-daycare",
    "pet boarding": "boarding-and-daycare",
    "kennels": "boarding-and-daycare",
    "pet waste removal": "pet-waste-removal",
    "pooper scooper": "pet-waste-removal",
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
    # 2026-06-11: existing leaves with no entry.
    "handyman": "handyman",
    "handymen": "handyman",
    "security systems": "security-and-alarms",
    "alarm companies": "security-and-alarms",
    # 2026-06-11: taxonomy-rebuild leaves (PENDING — self-activate at seed).
    "junk removal": "junk-removal-and-hauling",
    "junk hauling": "junk-removal-and-hauling",
    "pressure washing": "pressure-washing-and-exterior-cleaning",
    "power washing": "pressure-washing-and-exterior-cleaning",
    "mobile home repair": "mobile-home-services",
    "mobile home services": "mobile-home-services",
    "patio covers": "shade-screens-and-patio-covers",
    "sun screens": "shade-screens-and-patio-covers",
    "awnings": "shade-screens-and-patio-covers",
    "shade structures": "shade-screens-and-patio-covers",
    # Auto, RV & Marine
    "auto repair": "auto-repair",
    "mechanics": "auto-repair",
    "car repair": "auto-repair",
    "gas stations": "gas-stations",
    "car dealerships": "car-dealerships",
    # hunt 2026-06-10 §2: sweep n=25, no route
    "car dealer": "car-dealerships",
    "car dealers": "car-dealerships",
    "dealership": "car-dealerships",
    "dealerships": "car-dealerships",
    "auto parts": "auto-parts",
    "car wash": "car-wash",
    "car washes": "car-wash",
    "towing": "towing-and-roadside",
    "tow trucks": "towing-and-roadside",
    "car rentals": "car-rental",
    "tires": "tires",
    "tire shops": "tires",
    # 2026-06-11: existing leaves with no entry.
    # Detailing — the gerund ("detailing") AND the agent noun ("detailers")
    # are both high-traffic navigational asks; English inflection can't bridge
    # them, so both forms are listed explicitly. Boat/marine-qualified terms
    # route to the marine leaf; bare/auto/car terms route to the auto leaf.
    "detailing": "auto-detailing",
    "detailers": "auto-detailing",
    "detailer": "auto-detailing",
    "auto detailing": "auto-detailing",
    "auto detailers": "auto-detailing",
    "auto detailer": "auto-detailing",
    "car detailing": "auto-detailing",
    "car detailers": "auto-detailing",
    "mobile detailing": "auto-detailing",
    "mobile detailers": "auto-detailing",
    "boat detailing": "auto-marine-detailing",
    "boat detailers": "auto-marine-detailing",
    "boat detailer": "auto-marine-detailing",
    "marine detailing": "auto-marine-detailing",
    "watercraft detailing": "auto-marine-detailing",
    "boat repair": "boat-repair-and-service",
    "boat mechanics": "boat-repair-and-service",
    "boat sales": "boat-sales",
    "boat dealers": "boat-sales",
    "rv repair": "rv-sales-and-service",
    "rv service": "rv-sales-and-service",
    "rv sales": "rv-sales-and-service",
    "boat storage": "boat-and-rv-storage-service",
    "rv storage": "boat-and-rv-storage-service",
    "powersports": "powersports-and-atv",
    "atv rentals": "powersports-and-atv",
    "utv rentals": "powersports-and-atv",
    "shuttles": "shuttles-and-transportation",
    "taxis": "shuttles-and-transportation",
    # 2026-06-11: taxonomy-rebuild leaves (PENDING — self-activate at seed).
    "golf carts": "golf-carts",
    "golf cart repair": "golf-carts",
    "golf cart sales": "golf-carts",
    "auto glass": "auto-glass",
    "windshield repair": "auto-glass",
    "windshield replacement": "auto-glass",
    "window tint": "window-tint-and-wraps",
    "window tinting": "window-tint-and-wraps",
    "vehicle wraps": "window-tint-and-wraps",
    "car wraps": "window-tint-and-wraps",
    "trailer repair": "trailer-sales-and-repair",
    "trailer sales": "trailer-sales-and-repair",
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
    # 2026-06-11: existing leaves with no entry.
    "smoke shops": "smoke-vape-and-cannabis",
    "vape shops": "smoke-vape-and-cannabis",
    "dispensary": "smoke-vape-and-cannabis",
    "dispensaries": "smoke-vape-and-cannabis",
    "convenience stores": "convenience",
    "appliance stores": "appliances-and-electronics",
    "electronics stores": "appliances-and-electronics",
    "gift shops": "gifts-and-boutiques",
    "boutiques": "gifts-and-boutiques",
    "shoe stores": "shoes",
    "craft stores": "hobby-and-craft",
    "hobby shops": "hobby-and-craft",
    # 2026-06-11: taxonomy-rebuild leaf (PENDING).
    "gun stores": "firearms-and-shooting-sports",
    "gun shops": "firearms-and-shooting-sports",
    "firearms": "firearms-and-shooting-sports",
    "shooting range": "firearms-and-shooting-sports",
    "shooting ranges": "firearms-and-shooting-sports",
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
    # 2026-06-11: existing leaves with no entry.
    "computer repair": "computer-and-it-repair",
    "it support": "computer-and-it-repair",
    "print shops": "print-signs-and-marketing",
    "printing": "print-signs-and-marketing",
    "sign shops": "print-signs-and-marketing",
    "sign companies": "print-signs-and-marketing",
    "notaries": "notary",
    "notary": "notary",
    "title companies": "title-and-escrow",
    "escrow": "title-and-escrow",
    "shipping": "shipping-and-postal",
    "mailbox services": "shipping-and-postal",
    "event planners": "event-planning",
    "wedding planners": "event-planning",
    # 2026-06-11: taxonomy-rebuild leaves (PENDING — self-activate at seed).
    "property management": "property-management",
    "property managers": "property-management",
    "laundromat": "laundry-and-dry-cleaning",
    "laundromats": "laundry-and-dry-cleaning",
    "dry cleaners": "laundry-and-dry-cleaning",
    "dry cleaning": "laundry-and-dry-cleaning",
    # Family & Education
    "preschools": "preschools-and-childcare",
    "childcare": "preschools-and-childcare",
    "daycare": "preschools-and-childcare",
    "schools": "k-12-schools",
    # 2026-06-11
    "tutoring": "tutoring-and-test-prep",
    "tutors": "tutoring-and-test-prep",
    "music lessons": "music-lessons",
    # Community & Civic
    "churches": "places-of-worship",
    "libraries": "libraries",
    # 2026-06-11
    "community centers": "community-centers",
    "nonprofits": "nonprofits-and-charities",
    "charities": "nonprofits-and-charities",
    "mvd": "government-and-mvd",
    "dmv": "government-and-mvd",
    "post office": "post-office",
    "utilities": "utilities",
    # Lodging
    "hotels": "hotels-and-motels",
    "hotel": "hotels-and-motels",
    "motels": "hotels-and-motels",
    "lodging": "hotels-and-motels",
    "places to stay": "hotels-and-motels",
    "rv parks": "rv-parks-and-campgrounds",
    "campgrounds": "rv-parks-and-campgrounds",
    # 2026-06-11: taxonomy-rebuild leaf (PENDING).
    "funeral homes": "funeral-cremation-and-cemeteries",
    "funeral home": "funeral-cremation-and-cemeteries",
    "cremation": "funeral-cremation-and-cemeteries",
    "mortuaries": "funeral-cremation-and-cemeteries",
    "cemeteries": "funeral-cremation-and-cemeteries",
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

# Listing-shaped lead phrases ("i need a dog groomer", "looking for a plumber",
# "where can i find a vet"). Stripped BEFORE the navigational dict lookup so a
# plain category ask phrased as a need routes to the leaf page instead of a
# conversational turn. Mirrors (a subset of) the tier2_business_shortcut
# predicates — kept conservative: each alternative must be a pure "I want one
# of <category>" shape with no factual or temporal payload.
_LISTING_LEAD = re.compile(
    r"^\s*(?:"
    r"where\s+can\s+(?:i|we)\s+(?:find|get|hire|book)\s+|"
    r"i\s+(?:need|want)\s+(?:to\s+find\s+|to\s+get\s+)?|"
    r"i'?m\s+looking\s+for\s+|"
    r"we\s+(?:need|want)\s+|"
    r"looking\s+for\s+|"
    r"need\s+|"
    r"find\s+(?:me\s+)?|"
    r"got\s+any\s+|"
    r"are\s+there\s+(?:any\s+)?|"
    r"recommend\s+(?:me\s+)?|"
    r"do\s+you\s+(?:have|know)\s+(?:of\s+)?(?:any\s+)?"
    r")",
    re.IGNORECASE,
)

# Tokens that mean the query carries factual / temporal payload beyond "I want
# one of <category>" — those stay conversational (Tier 1 owns hours/phone,
# Tier 2 owns time windows). Checked against the raw lowercased query.
_CONVERSATIONAL_TOKENS = (
    "hour",
    "phone",
    "number",
    "address",
    "website",
    "open now",
    "open today",
    "tonight",
    "tomorrow",
    "rating",
    "review",
    "cost",
    "price",
    "cheap",
    "how much",
    "how late",
    "what time",
    "when do",
    "when does",
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
    return _leaf_for_normalized_term(db, norm)


def match_leaf_for_chat(db: Session, q: str | None) -> leaf_pages.Leaf | None:
    """Leaf-page match for in-thread chat turns — listing-shaped phrasings too.

    Extends :func:`match_leaf_query`: besides the exact navigational term
    ("dog groomers"), also matches need-shaped listing asks ("i need a dog
    groomer", "looking for a plumber") by stripping one listing lead phrase
    before the same exact-dict lookup. Queries carrying factual or temporal
    payload (hours, phone, "open now", "tonight") never match — those belong
    to the conversational tiers.
    """
    raw = (q or "").strip().lower()
    if not raw:
        return None
    if any(tok in raw for tok in _CONVERSATIONAL_TOKENS):
        return None
    norm = _normalize(raw)
    if norm:
        leaf = _leaf_for_normalized_term(db, norm)
        if leaf is not None:
            return leaf
    # Listing-shaped lead: strip it from the RAW query, then re-normalize.
    m = _LISTING_LEAD.match(raw)
    if not m:
        return None
    rest = raw[m.end() :].strip()
    if not rest:
        return None
    norm = _normalize(rest)
    if not norm:
        return None
    return _leaf_for_normalized_term(db, norm)


def _leaf_for_normalized_term(db: Session, norm: str) -> leaf_pages.Leaf | None:
    """Dict lookup + DB existence + thin-page gate for a normalized term."""
    slug = _QUERY_TO_LEAF.get(norm)
    if slug is None:
        return None
    leaf = leaf_pages.resolve_leaf_by_slug(db, slug)
    if leaf is None:
        return None
    if leaf_pages.leaf_renderable_count(db, leaf) < leaf_pages.LEAF_PAGE_MIN_PROVIDERS:
        return None
    return leaf
