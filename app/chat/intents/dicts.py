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

2026-06-11 expansion (intent-efficiency pass): SERVICE_DICT / CUISINE_DICT /
SYMPTOM_MAP grew to cover the verified coverage-gap trades from
``COVERAGE_GAP_AUDIT_2026-06-10.md`` and ``HAVA_AUDIT_AND_TAXONOMY_REBUILD.md``
(towing, detailing, wraps/tint, golf carts, property management, laundry,
hearing aids, funeral, junk removal, pressure washing, appliance/garage-door
repair, locksmiths, pet sitting, ...). Safe by construction: the intent layer
falls through on zero rows, so a dictionary entry whose trade has no catalog
coverage yet simply logs the demand signal to ``query_log`` and the legacy
path answers -- no wrong answers, no fabrication.
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

EAT_LEGACY_CATEGORIES: tuple[str, ...] = (
    "food_drink",
    "food",
    "restaurant",
    "bakery",
    "eat-drink",  # some rows carry the route slug as the category value
)
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

# On-the-water bucket: marinas, boat rental/repair, lake recreation. Subcat
# group "on-the-water" (recreation-outdoors) + the legacy category strings the
# loaders/backfill use (see app/categories/subcategories.py LEGACY_TO_SUBCAT).
WATER_LEGACY_CATEGORIES: tuple[str, ...] = (
    "lake_recreation",
    "boat_rental",
    "boat_repair",
    "on-the-water",
)
WATER_SUBCATS: tuple[str, ...] = ("on-the-water",)

# Parks / trails / beaches (recreation-outdoors). Legacy "recreation" backfills
# to "parks-beaches".
RECREATION_LEGACY_CATEGORIES: tuple[str, ...] = ("recreation",)
RECREATION_SUBCATS: tuple[str, ...] = ("parks-beaches", "trails-offroad")

# Civic & community: libraries, worship, non-profits, public services. Subcat
# group "civic-community"; legacy "religion_community".
CIVIC_LEGACY_CATEGORIES: tuple[str, ...] = ("religion_community",)
CIVIC_SUBCATS: tuple[str, ...] = ("civic-community",)


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
    # 2026-06-11 expansion -- home & property
    "pool repair": ServiceRoute("home-services", ("pool",)),
    "pool builder": ServiceRoute("home-services", ("pool",)),
    "appliance repair": ServiceRoute(
        "home-services", ("appliance", "refrigerat", "washer", "dryer")
    ),
    "garage door": ServiceRoute("home-services", ("garage door", "overhead door")),
    "garage door repair": ServiceRoute("home-services", ("garage door", "overhead door")),
    "tree service": ServiceRoute("home-services", ("tree", "stump")),
    "tree trimming": ServiceRoute("home-services", ("tree", "stump")),
    "tree removal": ServiceRoute("home-services", ("tree", "stump")),
    "junk removal": ServiceRoute("home-services", ("junk", "hauling", "haul")),
    "junk hauling": ServiceRoute("home-services", ("junk", "hauling", "haul")),
    "pressure washing": ServiceRoute("home-services", ("pressure wash", "power wash")),
    "power washing": ServiceRoute("home-services", ("pressure wash", "power wash")),
    "window cleaning": ServiceRoute("home-services", ("window clean",)),
    "carpet cleaning": ServiceRoute("home-services", ("carpet",)),
    "septic": ServiceRoute("home-services", ("septic",)),
    "septic pumping": ServiceRoute("home-services", ("septic",)),
    "welding": ServiceRoute("home-services", ("weld", "fabricat")),
    "fencing": ServiceRoute("home-services", ("fence", "fencing")),
    "fence company": ServiceRoute("home-services", ("fence", "fencing")),
    "flooring": ServiceRoute("home-services", ("floor", "tile")),
    "drywall": ServiceRoute("home-services", ("drywall",)),
    "concrete": ServiceRoute("home-services", ("concrete", "paving")),
    "home inspector": ServiceRoute("home-services", ("inspect",)),
    "home inspection": ServiceRoute("home-services", ("inspect",)),
    "locksmith": ServiceRoute("home-services", ("locksmith", "lock and key")),
    "movers": ServiceRoute("home-services", ("moving", "movers", "relocat")),
    "moving company": ServiceRoute("home-services", ("moving", "movers", "relocat")),
    "solar": ServiceRoute("home-services", ("solar",)),
    "solar installer": ServiceRoute("home-services", ("solar",)),
    "patio covers": ServiceRoute("home-services", ("patio cover", "awning", "shade", "screen")),
    "sun screens": ServiceRoute("home-services", ("screen", "shade", "awning")),
    "awnings": ServiceRoute("home-services", ("awning", "patio cover", "shade")),
    "mobile home repair": ServiceRoute(
        "home-services", ("mobile home", "manufactured home")
    ),
    "mobile home services": ServiceRoute(
        "home-services", ("mobile home", "manufactured home")
    ),
    "propane": ServiceRoute("home-services", ("propane",)),
    # -- Auto --
    "mechanic": ServiceRoute("auto", ("mechanic", "auto repair", "car repair"), ("auto",)),
    "auto repair": ServiceRoute("auto", ("auto repair", "car repair", "mechanic"), ("auto",)),
    "oil change": ServiceRoute("auto", ("oil change", "lube"), ("auto",)),
    "tire shop": ServiceRoute("auto", ("tire",), ("auto",)),
    "tires": ServiceRoute("auto", ("tire",), ("auto",)),
    "car wash": ServiceRoute("auto", ("car wash", "wash"), ("auto",)),
    "auto body": ServiceRoute("auto", ("body shop", "collision", "auto body"), ("auto",)),
    "rv repair": ServiceRoute("auto", ("rv", "recreational vehicle"), ("auto",)),
    # 2026-06-11 expansion -- auto, rv & marine
    "towing": ServiceRoute("auto", ("towing", "tow", "wrecker"), ("auto",)),
    "tow truck": ServiceRoute("auto", ("towing", "tow", "wrecker"), ("auto",)),
    "roadside assistance": ServiceRoute("auto", ("towing", "roadside", "wrecker"), ("auto",)),
    "auto glass": ServiceRoute("auto", ("windshield", "auto glass", "glass"), ("auto",)),
    "windshield repair": ServiceRoute("auto", ("windshield", "auto glass", "glass"), ("auto",)),
    "windshield replacement": ServiceRoute(
        "auto", ("windshield", "auto glass", "glass"), ("auto",)
    ),
    "windshield": ServiceRoute("auto", ("windshield", "auto glass", "glass"), ("auto",)),
    "window tint": ServiceRoute("auto", ("tint",), ("auto",)),
    "tinting": ServiceRoute("auto", ("tint",), ("auto",)),
    "tint shop": ServiceRoute("auto", ("tint",), ("auto",)),
    "vehicle wrap": ServiceRoute("auto", ("wrap", "graphic", "sign"), ("auto",)),
    "vehicle wraps": ServiceRoute("auto", ("wrap", "graphic", "sign"), ("auto",)),
    "car wrap": ServiceRoute("auto", ("wrap", "graphic", "sign"), ("auto",)),
    "car wraps": ServiceRoute("auto", ("wrap", "graphic", "sign"), ("auto",)),
    "boat wrap": ServiceRoute("auto", ("wrap", "graphic", "sign"), ("auto",)),
    # Detailing spans auto + marine rows; the legacy water categories keep
    # boat detailers reachable ("boat detail and wash" -> Detail Specialties).
    "detailing": ServiceRoute(
        "auto", ("detail",), ("auto", "lake_recreation", "boat_rental", "boat_repair")
    ),
    "auto detailing": ServiceRoute(
        "auto", ("detail",), ("auto", "lake_recreation", "boat_rental", "boat_repair")
    ),
    "car detailing": ServiceRoute(
        "auto", ("detail",), ("auto", "lake_recreation", "boat_rental", "boat_repair")
    ),
    "boat detailing": ServiceRoute(
        "auto", ("detail",), ("auto", "lake_recreation", "boat_rental", "boat_repair")
    ),
    "mobile detailing": ServiceRoute(
        "auto", ("detail",), ("auto", "lake_recreation", "boat_rental", "boat_repair")
    ),
    "detail shop": ServiceRoute(
        "auto", ("detail",), ("auto", "lake_recreation", "boat_rental", "boat_repair")
    ),
    "golf cart": ServiceRoute("auto", ("golf cart",), ("auto",)),
    "golf carts": ServiceRoute("auto", ("golf cart",), ("auto",)),
    "golf cart repair": ServiceRoute("auto", ("golf cart",), ("auto",)),
    "trailer repair": ServiceRoute("auto", ("trailer",), ("auto",)),
    "trailer sales": ServiceRoute("auto", ("trailer",), ("auto",)),
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
    # 2026-06-11 expansion -- health & medical
    "hearing aids": ServiceRoute("health-medical", ("hearing", "audiolog")),
    "hearing aid": ServiceRoute("health-medical", ("hearing", "audiolog")),
    "audiologist": ServiceRoute("health-medical", ("hearing", "audiolog")),
    "hearing test": ServiceRoute("health-medical", ("hearing", "audiolog")),
    "dermatologist": ServiceRoute("health-medical", ("derm", "skin")),
    "skin doctor": ServiceRoute("health-medical", ("derm", "skin")),
    "counselor": ServiceRoute(
        "health-medical", ("counsel", "therap", "mental", "psych", "behavioral")
    ),
    "counseling": ServiceRoute(
        "health-medical", ("counsel", "therap", "mental", "psych", "behavioral")
    ),
    "therapist": ServiceRoute(
        "health-medical", ("counsel", "therap", "mental", "psych", "behavioral")
    ),
    "mental health": ServiceRoute(
        "health-medical", ("counsel", "therap", "mental", "psych", "behavioral")
    ),
    "imaging": ServiceRoute("health-medical", ("imaging", "radiolog", "x-ray", "xray")),
    "dialysis": ServiceRoute("health-medical", ("dialysis",)),
    "home health": ServiceRoute("health-medical", ("home health", "hospice")),
    "hospice": ServiceRoute("health-medical", ("hospice", "home health")),
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
    # 2026-06-11 expansion -- professional & financial
    "property management": ServiceRoute(
        "professional", ("property manag", "rental manag"), ("professional_services",)
    ),
    "property manager": ServiceRoute(
        "professional", ("property manag", "rental manag"), ("professional_services",)
    ),
    "laundromat": ServiceRoute(
        "professional", ("laundr", "wash and fold", "dry clean"), ("professional_services",)
    ),
    "laundry": ServiceRoute(
        "professional", ("laundr", "wash and fold", "dry clean"), ("professional_services",)
    ),
    "wash and fold": ServiceRoute(
        "professional", ("laundr", "wash and fold", "dry clean"), ("professional_services",)
    ),
    "dry cleaning": ServiceRoute(
        "professional", ("dry clean", "laundr", "cleaners"), ("professional_services",)
    ),
    "dry cleaner": ServiceRoute(
        "professional", ("dry clean", "laundr", "cleaners"), ("professional_services",)
    ),
    "notary": ServiceRoute("professional", ("notary",), ("professional_services",)),
    "title company": ServiceRoute(
        "professional", ("title", "escrow"), ("professional_services",)
    ),
    "escrow": ServiceRoute("professional", ("title", "escrow"), ("professional_services",)),
    "computer repair": ServiceRoute(
        "professional", ("computer", "laptop", "tech repair"), ("professional_services",)
    ),
    "it support": ServiceRoute(
        "professional", ("computer", "tech", "it service"), ("professional_services",)
    ),
    "phone repair": ServiceRoute(
        "professional", ("phone repair", "cell phone", "iphone"), ("professional_services",)
    ),
    "sign shop": ServiceRoute(
        "professional", ("sign", "banner", "graphic", "print"), ("professional_services",)
    ),
    "sign company": ServiceRoute(
        "professional", ("sign", "banner", "graphic", "print"), ("professional_services",)
    ),
    "business signs": ServiceRoute(
        "professional", ("sign", "banner", "graphic", "print"), ("professional_services",)
    ),
    "custom signs": ServiceRoute(
        "professional", ("sign", "banner", "graphic", "print"), ("professional_services",)
    ),
    "print shop": ServiceRoute(
        "professional", ("print", "sign", "banner", "graphic"), ("professional_services",)
    ),
    "printing": ServiceRoute(
        "professional", ("print", "sign", "banner", "graphic"), ("professional_services",)
    ),
    "event planner": ServiceRoute(
        "professional", ("event plan", "wedding"), ("professional_services",)
    ),
    "event planning": ServiceRoute(
        "professional", ("event plan", "wedding"), ("professional_services",)
    ),
    "wedding planner": ServiceRoute(
        "professional", ("event plan", "wedding"), ("professional_services",)
    ),
    "shipping": ServiceRoute(
        "professional", ("ship", "mail", "pack", "postal"), ("professional_services",)
    ),
    # -- Pets --
    "vet": ServiceRoute("pets", ("vet", "animal hospital", "veterin")),
    "veterinarian": ServiceRoute("pets", ("vet", "animal hospital", "veterin")),
    "groomer": ServiceRoute("pets", ("groom",)),
    "dog grooming": ServiceRoute("pets", ("groom",)),
    "pet boarding": ServiceRoute("pets", ("boarding", "kennel")),
    "kennel": ServiceRoute("pets", ("boarding", "kennel")),
    # 2026-06-11 expansion -- pets
    "pet sitting": ServiceRoute("pets", ("sitt", "walk", "board")),
    "pet sitter": ServiceRoute("pets", ("sitt", "walk", "board")),
    "dog sitter": ServiceRoute("pets", ("sitt", "walk", "board")),
    "cat sitter": ServiceRoute("pets", ("sitt", "walk", "board")),
    "dog walker": ServiceRoute("pets", ("walk", "sitt")),
    "dog walking": ServiceRoute("pets", ("walk", "sitt")),
    "pet waste removal": ServiceRoute("pets", ("scoop", "poop", "waste")),
    "pooper scooper": ServiceRoute("pets", ("scoop", "poop", "waste")),
    # -- Beauty & personal care --
    "salon": ServiceRoute("beauty", ("salon", "hair")),
    "hair salon": ServiceRoute("beauty", ("salon", "hair")),
    "barber": ServiceRoute("beauty", ("barber",)),
    "nail salon": ServiceRoute("beauty", ("nail",)),
    "nails": ServiceRoute("beauty", ("nail",)),
    "spa": ServiceRoute("beauty", ("spa", "massage")),
    "massage": ServiceRoute("beauty", ("massage", "spa")),
    # 2026-06-11 expansion -- beauty & personal care
    "tattoo": ServiceRoute("beauty", ("tattoo", "ink", "piercing")),
    "tattoo shop": ServiceRoute("beauty", ("tattoo", "ink", "piercing")),
    "piercing": ServiceRoute("beauty", ("piercing", "tattoo")),
    "tanning": ServiceRoute("beauty", ("tanning",)),
    "med spa": ServiceRoute("beauty", ("med spa", "aesthetic", "botox")),
    "med spas": ServiceRoute("beauty", ("med spa", "aesthetic", "botox")),
    "medical spa": ServiceRoute("beauty", ("med spa", "aesthetic", "botox")),
    "botox": ServiceRoute("beauty", ("med spa", "aesthetic", "botox")),
    # -- Storage --
    "storage": ServiceRoute("storage", ("storage",)),
    "self storage": ServiceRoute("storage", ("storage",)),
    # 2026-06-11 expansion -- storage
    "boat storage": ServiceRoute("storage", ("storage", "boat", "rv")),
    "rv storage": ServiceRoute("storage", ("storage", "boat", "rv")),
    "storage unit": ServiceRoute("storage", ("storage",)),
    "storage units": ServiceRoute("storage", ("storage",)),
    # -- Civic / community --
    # 2026-06-11 expansion -- funeral & end-of-life (5 named local operators,
    # coverage audit §2; listing-only).
    "funeral": ServiceRoute(
        "civic-community",
        ("funeral", "cremation", "mortuary", "cemetery"),
        ("religion_community", "professional_services"),
    ),
    "funeral home": ServiceRoute(
        "civic-community",
        ("funeral", "cremation", "mortuary", "cemetery"),
        ("religion_community", "professional_services"),
    ),
    "funeral homes": ServiceRoute(
        "civic-community",
        ("funeral", "cremation", "mortuary", "cemetery"),
        ("religion_community", "professional_services"),
    ),
    "cremation": ServiceRoute(
        "civic-community",
        ("funeral", "cremation", "mortuary", "cemetery"),
        ("religion_community", "professional_services"),
    ),
    "mortuary": ServiceRoute(
        "civic-community",
        ("funeral", "cremation", "mortuary", "cemetery"),
        ("religion_community", "professional_services"),
    ),
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
    "mexican": ("mexican", "taco", "tacos", "taqueria", "cantina", "burrito", "burritos"),
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
    # 2026-06-06 gap-report widening: recurring tier-3 phrasings with real
    # catalog coverage (bars-breweries / quick-bites subcats).
    "happy hour": ("bar", "pub", "tavern", "lounge", "brew", "saloon", "grill", "cocktail"),
    "quick bites": ("burger", "pizza", "taco", "sandwich", "deli", "fast food", "hot dog", "wing"),
    "quick bite": ("burger", "pizza", "taco", "sandwich", "deli", "fast food", "hot dog", "wing"),
    # 2026-06-11 expansion: cuisines/forms users actually type that previously
    # fell through to Tier 3. Name tokens only -- grounded the same way as the
    # originals.
    "steak": ("steak", "chophouse"),
    "wings": ("wing", "wings"),
    "sandwich": ("sandwich", "deli", "sub", "subway", "hoagie"),
    "sandwiches": ("sandwich", "deli", "sub", "subway", "hoagie"),
    "deli": ("deli", "sandwich"),
    "sub shop": ("sub", "sandwich", "deli"),
    "ice cream": ("ice cream", "gelato", "yogurt", "creamery", "shaved ice", "snow cone"),
    "gelato": ("gelato", "ice cream"),
    "frozen yogurt": ("yogurt", "froyo", "ice cream"),
    "shaved ice": ("shaved ice", "snow cone", "ice"),
    "donuts": ("donut", "doughnut"),
    "donut": ("donut", "doughnut"),
    "doughnuts": ("donut", "doughnut"),
    "greek": ("greek", "gyro", "mediterranean", "kebab"),
    "gyros": ("gyro", "greek", "mediterranean"),
    "mediterranean": ("mediterranean", "greek", "gyro", "kebab"),
    "indian": ("indian", "curry", "tandoor"),
    "vietnamese": ("pho", "vietnam"),
    "pho": ("pho", "vietnam"),
    "korean": ("korean",),
    "hawaiian": ("hawaiian", "poke", "aloha"),
    "poke": ("poke", "hawaiian"),
    "fish and chips": ("fish", "chips", "cod"),
    "wine": ("wine", "vino", "cellar"),
    "wine bar": ("wine", "vino", "cellar"),
    "winery": ("wine", "vino", "cellar"),
    "cocktails": ("cocktail", "lounge", "mixology"),
    "cocktail bar": ("cocktail", "lounge", "mixology"),
    "sports bar": ("sports bar", "sports grill", "wing"),
    "vegan": ("vegan", "vegetarian", "plant based"),
    "vegetarian": ("vegetarian", "vegan", "plant based"),
    "smoothies": ("smoothie", "juice", "acai"),
    "smoothie": ("smoothie", "juice", "acai"),
    "juice bar": ("juice", "smoothie", "acai"),
    "food truck": ("food truck",),
    "food trucks": ("food truck",),
    "catering": ("catering", "caterer"),
    "caterer": ("catering", "caterer"),
}

# Cuisine subgroups that map to a subcategory chip rather than a name token.
CUISINE_TO_SUBCAT: dict[str, str] = {
    "coffee": "cafes-coffee",
    "cafe": "cafes-coffee",
    "bakery": "cafes-coffee",
    "bar": "bars-breweries",
    "brewery": "bars-breweries",
    "happy hour": "bars-breweries",
    "quick bites": "quick-bites",
    "quick bite": "quick-bites",
    # 2026-06-11 expansion
    "sandwich": "quick-bites",
    "sandwiches": "quick-bites",
    "deli": "quick-bites",
    "sub shop": "quick-bites",
    "ice cream": "quick-bites",
    "donuts": "cafes-coffee",
    "donut": "cafes-coffee",
    "doughnuts": "cafes-coffee",
    "smoothies": "cafes-coffee",
    "smoothie": "cafes-coffee",
    "juice bar": "cafes-coffee",
    "wine": "bars-breweries",
    "wine bar": "bars-breweries",
    "winery": "bars-breweries",
    "cocktails": "bars-breweries",
    "cocktail bar": "bars-breweries",
    "sports bar": "bars-breweries",
    "food truck": "quick-bites",
    "food trucks": "quick-bites",
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
    # 2026-06-11 expansion: still listing-only, still conservative.
    "stitches": SymptomRoute(("urgent", "walk-in", "walk in")),
    "sprained ankle": SymptomRoute(("urgent", "walk-in", "walk in")),
    "sprain": SymptomRoute(("urgent", "walk-in", "walk in")),
    "pink eye": SymptomRoute(("urgent", "walk-in", "walk in")),
    "flu shot": SymptomRoute(("pharmacy", "drug")),
    "vaccine": SymptomRoute(("pharmacy", "drug")),
    "vaccination": SymptomRoute(("pharmacy", "drug")),
    "tooth hurts": SymptomRoute(("dental", "dentist")),
    "cracked tooth": SymptomRoute(("dental", "dentist")),
    "sports physical": SymptomRoute(("clinic", "urgent", "medical")),
    "blood work": SymptomRoute(("lab", "clinic")),
    "lab work": SymptomRoute(("lab", "clinic")),
}
