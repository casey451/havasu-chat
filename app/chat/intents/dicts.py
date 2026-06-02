"""Controlled dictionaries for L2 slot-fill (Ask Hava intent catalog, Phase 1).

Every mapping here is grounded in real, queryable fields:

* ``SERVICE_DICT`` -> ``Provider.subcategory`` group slugs from
  ``app/categories/subcategories.py`` (Services groups: home-services, auto,
  health-medical, professional, pets, beauty, storage, civic-community), plus
  name/category tokens for the sub-trade granularity that ``subcategory`` alone
  cannot express (a plumber and an electrician are both ``home-services``).
* ``CUISINE_DICT`` -> name-token sets matched within the eat-drink categories.
  There is no cuisine field, so cuisine is a name-token match (master spec §16
  Q4) -- the tokens are the grounding.
* ``AREA_DICT`` -> ``Provider.district`` (ilike-contains, so partial labels
  still match). District values/coverage are a Phase-0 data check; matching is
  deliberately fuzzy so a thin district column degrades gracefully.
* ``AGE_BANDS`` / ``parse_age_band`` -> numeric bands for ``Program.age_min`` /
  ``Program.age_max``. "my 8-year-old" and "for a 9 year old" must both
  normalize to ``kids`` (master spec §4.2).
* ``SYMPTOM_MAP`` -> health-medical listings only (never diagnostic).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Real legacy Provider.category slug groups (from CATEGORY_FILTERS + the
# subcategories backfill map). Used so a query can match either the coarse
# legacy ``category`` string OR the newer ``subcategory`` group slug -- some
# rows are only labeled at one level.
# ---------------------------------------------------------------------------

EAT_LEGACY_CATEGORIES: tuple[str, ...] = ("food_drink", "food", "restaurant", "bakery")
EAT_SUBCATS: tuple[str, ...] = (
    "restaurants",
    "bars-breweries",
    "cafes-coffee",
    "quick-bites",
)

STAY_LEGACY_CATEGORIES: tuple[str, ...] = ("lodging", "lodging_vacation_rentals")
STAY_SUBCATS: tuple[str, ...] = ("hotels", "vacation-rentals", "rv-parks")

SHOPPING_LEGACY_CATEGORIES: tuple[str, ...] = ("retail", "shopping_essentials")
SHOPPING_SUBCATS: tuple[str, ...] = ("boutiques", "home-goods", "specialty", "markets")


@dataclass(frozen=True)
class ServiceRoute:
    """How a service term resolves against the catalog.

    ``subcat`` is the ``Provider.subcategory`` group (coarse). ``name_tokens``
    narrow within that group by ilike-matching ``provider_name`` /
    ``google_primary_category`` -- this is the only place per-trade granularity
    exists, since ``subcategory`` collapses plumber+electrician into
    ``home-services``.
    """

    subcat: str
    name_tokens: tuple[str, ...]
    legacy_categories: tuple[str, ...] = ()


# Service term (and common variants) -> route. Subcat slugs are exactly the
# Services groups in app/categories/subcategories.py.
SERVICE_DICT: dict[str, ServiceRoute] = {
    # -- Home services --
    "plumber": ServiceRoute("home-services", ("plumb",)),
    "plumbing": ServiceRoute("home-services", ("plumb",)),
    "electrician": ServiceRoute("home-services", ("electric",)),
    "electrical": ServiceRoute("home-services", ("electric",)),
    "hvac": ServiceRoute("home-services", ("hvac", "air condition", "heating", "cooling")),
    "ac repair": ServiceRoute("home-services", ("hvac", "air condition", "cooling")),
    "air conditioning": ServiceRoute("home-services", ("hvac", "air condition", "cooling")),
    "roofer": ServiceRoute("home-services", ("roof",)),
    "roofing": ServiceRoute("home-services", ("roof",)),
    "handyman": ServiceRoute("home-services", ("handyman", "handy man")),
    "contractor": ServiceRoute("home-services", ("contractor", "construction")),
    "general contractor": ServiceRoute("home-services", ("contractor", "construction")),
    "landscaper": ServiceRoute("home-services", ("landscap", "lawn")),
    "landscaping": ServiceRoute("home-services", ("landscap", "lawn")),
    "house cleaning": ServiceRoute("home-services", ("clean",)),
    "cleaner": ServiceRoute("home-services", ("clean",)),
    "pest control": ServiceRoute("home-services", ("pest",)),
    "painter": ServiceRoute("home-services", ("paint",)),
    "pool service": ServiceRoute("home-services", ("pool",)),
    # -- Auto --
    "mechanic": ServiceRoute("auto", ("mechanic", "auto repair", "car repair"), ("auto",)),
    "auto repair": ServiceRoute("auto", ("auto repair", "car repair", "mechanic"), ("auto",)),
    "oil change": ServiceRoute("auto", ("oil change", "lube"), ("auto",)),
    "tire shop": ServiceRoute("auto", ("tire",), ("auto",)),
    "tires": ServiceRoute("auto", ("tire",), ("auto",)),
    "car wash": ServiceRoute("auto", ("car wash", "wash"), ("auto",)),
    "auto body": ServiceRoute("auto", ("body shop", "collision", "auto body"), ("auto",)),
    "rv repair": ServiceRoute("auto", ("rv", "recreational vehicle"), ("auto",)),
    # -- Health & medical (listing only) --
    "dentist": ServiceRoute("health-medical", ("dental", "dentist")),
    "dental": ServiceRoute("health-medical", ("dental", "dentist")),
    "doctor": ServiceRoute("health-medical", ("doctor", "physician", "clinic", "medical")),
    "clinic": ServiceRoute("health-medical", ("clinic", "urgent", "medical")),
    "chiropractor": ServiceRoute("health-medical", ("chiro",)),
    "optometrist": ServiceRoute("health-medical", ("optom", "eye", "vision")),
    "eye doctor": ServiceRoute("health-medical", ("optom", "eye", "vision")),
    "pharmacy": ServiceRoute("health-medical", ("pharmacy", "drug")),
    "physical therapy": ServiceRoute("health-medical", ("physical therap", "physiotherap", "rehab")),
    # -- Professional --
    "lawyer": ServiceRoute("professional", ("law", "attorney", "legal")),
    "attorney": ServiceRoute("professional", ("law", "attorney", "legal")),
    "realtor": ServiceRoute("professional", ("real estate", "realty", "realtor")),
    "real estate agent": ServiceRoute("professional", ("real estate", "realty", "realtor")),
    "insurance": ServiceRoute("professional", ("insurance",)),
    "accountant": ServiceRoute("professional", ("account", "cpa", "tax")),
    "cpa": ServiceRoute("professional", ("account", "cpa", "tax")),
    "financial advisor": ServiceRoute("professional", ("financial", "wealth", "advisor")),
    "tax preparer": ServiceRoute("professional", ("tax", "account")),
    # -- Pets --
    "vet": ServiceRoute("pets", ("vet", "animal hospital", "veterin")),
    "veterinarian": ServiceRoute("pets", ("vet", "animal hospital", "veterin")),
    "groomer": ServiceRoute("pets", ("groom",)),
    "dog grooming": ServiceRoute("pets", ("groom",)),
    "pet boarding": ServiceRoute("pets", ("boarding", "kennel")),
    "kennel": ServiceRoute("pets", ("boarding", "kennel")),
    # -- Beauty & personal care --
    "salon": ServiceRoute("beauty", ("salon", "hair")),
    "hair salon": ServiceRoute("beauty", ("salon", "hair")),
    "barber": ServiceRoute("beauty", ("barber",)),
    "nail salon": ServiceRoute("beauty", ("nail",)),
    "nails": ServiceRoute("beauty", ("nail",)),
    "spa": ServiceRoute("beauty", ("spa", "massage")),
    "massage": ServiceRoute("beauty", ("massage", "spa")),
    # -- Storage --
    "storage": ServiceRoute("storage", ("storage",)),
    "self storage": ServiceRoute("storage", ("storage",)),
}

# All Services subcategory groups -- used by tests to assert SERVICE_DICT only
# routes to real groups.
SERVICE_SUBCAT_GROUPS: frozenset[str] = frozenset(
    {
        "home-services",
        "auto",
        "health-medical",
        "professional",
        "pets",
        "beauty",
        "storage",
        "civic-community",
    }
)


# Cuisine / drink term -> name tokens matched within eat-drink. No cuisine
# field exists; this is a name-token match (master spec §16 Q4).
CUISINE_DICT: dict[str, tuple[str, ...]] = {
    "mexican": ("mexican", "taco", "taqueria", "cantina", "burrito"),
    "bbq": ("bbq", "barbecue", "barbeque", "smokehouse"),
    "barbecue": ("bbq", "barbecue", "smokehouse"),
    "pizza": ("pizza", "pizzeria"),
    "italian": ("italian", "pasta", "trattoria"),
    "seafood": ("seafood", "fish", "oyster"),
    "sushi": ("sushi", "japanese", "ramen"),
    "chinese": ("chinese", "wok"),
    "thai": ("thai",),
    "burger": ("burger",),
    "burgers": ("burger",),
    "steakhouse": ("steak", "chophouse"),
    "coffee": ("coffee", "cafe", "espresso", "roaster"),
    "cafe": ("cafe", "coffee", "espresso"),
    "bar": ("bar", "pub", "tavern", "lounge"),
    "brewery": ("brew", "beer", "taproom", "ale"),
    "bakery": ("bakery", "bake", "pastry", "donut", "doughnut"),
    "breakfast": ("breakfast", "brunch", "diner"),
    "brunch": ("brunch", "breakfast"),
}

# Cuisine subgroups that map to a subcategory chip rather than a name token.
CUISINE_TO_SUBCAT: dict[str, str] = {
    "coffee": "cafes-coffee",
    "cafe": "cafes-coffee",
    "bakery": "cafes-coffee",
    "bar": "bars-breweries",
    "brewery": "bars-breweries",
}


# Neighborhood phrase -> district token (ilike-contains against
# Provider.district). Provisional labels drawn from the live filter chips;
# district coverage + exact values are a Phase-0 data check. Fuzzy contains
# means a slightly different stored label still matches.
AREA_DICT: dict[str, str] = {
    "english village": "English Village",
    "downtown": "Downtown",
    "main street": "Downtown",
    "uptown": "Uptown",
    "north end": "North",
    "lakefront": "Lakefront",
    "lake front": "Lakefront",
    "on the lake": "Lakefront",
    "mesquite bay": "Mesquite",
    "highway 95": "95",
    "the island": "Island",
    "site six": "Site Six",
    "pittsburgh point": "Pittsburgh Point",
    "castle rock": "Castle Rock",
    "south side": "South",
}


# Age band -> inclusive (min_age, max_age). 200 is an open-ended upper bound.
AGE_BANDS: dict[str, tuple[int, int]] = {
    "toddler": (1, 3),
    "kids": (4, 12),
    "teen": (13, 17),
    "adult": (18, 200),
    "senior": (55, 200),
}

_AGE_NUMBER_RE = re.compile(
    r"\b(\d{1,2})\s*(?:-|\s)?\s*(?:year|yr|yrs|years)?\s*[- ]?\s*old\b",
)
_AGE_OF_RE = re.compile(r"\bage[ds]?\s+(\d{1,2})\b")

_TODDLER_WORDS = ("toddler", "preschool", "pre-school", "infant", "baby")
_KID_WORDS = ("kid", "kids", "child", "children", "youth", "elementary", "grade school")
_TEEN_WORDS = ("teen", "teens", "teenager", "high school", "highschool")
_SENIOR_WORDS = ("senior", "seniors", "older adult", "55+", "55 plus")
_ADULT_WORDS = ("adult", "adults", "grown up", "grown-up")


def _band_for_age(age: int) -> str:
    for band, (lo, hi) in AGE_BANDS.items():
        if band == "adult":
            continue  # adult overlaps senior at the top; check word-based path first
        if lo <= age <= hi:
            return band
    return "adult"


def parse_age_band(text: str) -> str | None:
    """Normalize age phrasing to a band slug, or None.

    Numeric ages win (so "my 8-year-old" and "for a 9 year old" both -> kids,
    master spec §4.2). Falls back to age keywords.
    """
    lowered = (text or "").lower()

    m = _AGE_NUMBER_RE.search(lowered) or _AGE_OF_RE.search(lowered)
    if m:
        try:
            return _band_for_age(int(m.group(1)))
        except (ValueError, IndexError):
            pass

    if any(w in lowered for w in _TODDLER_WORDS):
        return "toddler"
    if any(w in lowered for w in _TEEN_WORDS):
        return "teen"
    if any(w in lowered for w in _SENIOR_WORDS):
        return "senior"
    if any(w in lowered for w in _KID_WORDS):
        return "kids"
    if any(w in lowered for w in _ADULT_WORDS):
        return "adult"
    return None


def age_band_range(band: str | None) -> tuple[int, int] | None:
    if not band:
        return None
    return AGE_BANDS.get(band)


@dataclass(frozen=True)
class SymptomRoute:
    """Lay need -> a health-medical listing (never medical advice)."""

    name_tokens: tuple[str, ...]


# Conservative lay-need -> health listing tokens. Routes to a listing only.
SYMPTOM_MAP: dict[str, SymptomRoute] = {
    "urgent care": SymptomRoute(("urgent", "walk-in", "walk in")),
    "walk in clinic": SymptomRoute(("urgent", "walk-in", "walk in", "clinic")),
    "toothache": SymptomRoute(("dental", "dentist")),
    "tooth pain": SymptomRoute(("dental", "dentist")),
    "broken tooth": SymptomRoute(("dental", "dentist")),
    "eye exam": SymptomRoute(("optom", "eye", "vision")),
    "prescription": SymptomRoute(("pharmacy", "drug")),
    "refill": SymptomRoute(("pharmacy", "drug")),
}
