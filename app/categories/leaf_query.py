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
        # 2026-06-19 monetization pass: the high-ad-value Havasu trades below were
        # promoted into docs/proposals/taxonomy-seed.json (so the leaf rows seed
        # and the synonyms self-activate once providers are backfilled), and so
        # are NO LONGER pending — they live in the seed now:
        #   hearing-and-audiology, golf-carts, auto-glass, window-tint-and-wraps,
        #   trailer-sales-and-repair, property-management, junk-removal-and-hauling,
        #   pressure-washing-and-exterior-cleaning, shade-screens-and-patio-covers,
        #   off-road-shops-and-accessories, marine-supply, garage-doors, painters.
        # These remain genuinely unseeded (synonyms are deliberate no-ops until a
        # future taxonomy pass seeds them):
        "medical-specialists-and-imaging",
        "laundry-and-dry-cleaning",
        "funeral-cremation-and-cemeteries",
        "mobile-home-services",
        "pet-waste-removal",
        "firearms-and-shooting-sports",
        # 2026-06-20 search-coverage: brand-new service leaves with no taxonomy
        # home yet. Created by scripts/create_missing_service_leaves_2026_06_20.py;
        # routed below. Self-activate once the leaf clears the publish gate in
        # leaf_pages.LEAF_PAGE_MIN_PROVIDERS renderable listings (via
        # _resolve_gated) — so the Step-3 backfill must seed each leaf with
        # enough approved businesses to clear that threshold, not just one row.
        # (garage-doors + painters are intentionally NOT here — the 2026-06-19
        # pass already seeded them above, so they are live, not pending.)
        # 2026-07-01 consolidated audit A2: pediatricians leave the 159-row
        # primary-care leaf for their own home; seeded by the Phase-3 data op.
        "pediatrics",
        "locksmiths",
        "flooring",
        "fencing",
        "concrete-and-masonry",
        "drywall",
        "carpentry-and-cabinets",
        "welding-and-fabrication",
        "gutters",
        "windows-and-doors",
        "appliance-repair",
        "liquor-stores",
        "pawn-shops",
        "nurseries-and-garden-centers",
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
    # 2026-06-19: marine retail (boat parts/supplies) — distinct from boat
    # rentals/sales/repair. NEW leaf seeded under On the Water.
    "marine supply": "marine-supply",
    "marine supplies": "marine-supply",
    "marine store": "marine-supply",
    "boat parts": "marine-supply",
    "boat supplies": "marine-supply",
    "boat accessories": "marine-supply",
    # Outdoors & Recreation
    "parks": "parks-and-playgrounds",
    "golf courses": "golf-courses",
    "golf course": "golf-courses",
    "golf": "golf-courses",
    # 2026-06-19: golf-courses is the combined Golf hub — range/Toptracer +
    # indoor simulators route here too.
    "driving range": "golf-courses",
    "driving ranges": "golf-courses",
    "golf simulator": "golf-courses",
    "golf simulators": "golf-courses",
    "indoor golf": "golf-courses",
    "virtual golf": "golf-courses",
    "toptracer": "golf-courses",
    "top tracer": "golf-courses",
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
    "pool cleaner": "pools-and-spas",
    "pool cleaners": "pools-and-spas",
    "pool maintenance": "pools-and-spas",
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
    # 2026-06-19: NEW high-ad-value home-services leaves (seeded).
    "garage doors": "garage-doors",
    "garage door": "garage-doors",
    "garage door repair": "garage-doors",
    "garage door installation": "garage-doors",
    "painters": "painters",
    "painter": "painters",
    "house painters": "painters",
    "painting contractor": "painters",
    "painting contractors": "painters",
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
    # 2026-06-19: off-road RETAIL/upfit shops (parts, accessories, lift kits) —
    # Casey's "off road stores and sales". Distinct from off-road-and-ohv (trails)
    # and powersports-and-atv (vehicle sales/rentals). NEW leaf under Auto, RV & Marine.
    "off road shop": "off-road-shops-and-accessories",
    "off road shops": "off-road-shops-and-accessories",
    "off road store": "off-road-shops-and-accessories",
    "off road stores": "off-road-shops-and-accessories",
    "off road accessories": "off-road-shops-and-accessories",
    "off road parts": "off-road-shops-and-accessories",
    "utv accessories": "off-road-shops-and-accessories",
    "utv parts": "off-road-shops-and-accessories",
    "lift kits": "off-road-shops-and-accessories",
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
    # 2026-06-30 audit 3D: cannabis dispensaries split into their own leaf so the
    # 2 real dispensaries aren't buried among the vape shops. Dispensary/cannabis
    # terms route to the new leaf; smoke/vape terms stay above.
    "dispensary": "cannabis-dispensaries",
    "dispensaries": "cannabis-dispensaries",
    "cannabis": "cannabis-dispensaries",
    "cannabis dispensary": "cannabis-dispensaries",
    "marijuana": "cannabis-dispensaries",
    "marijuana dispensary": "cannabis-dispensaries",
    "weed": "cannabis-dispensaries",
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

# ---------------------------------------------------------------------------
# 2026-06-20 search-coverage expansion. Casey: typing "pool builders" /
# "pool cleaners" (and many other plain service terms) returned "sorry, no
# results" because only a narrow set of phrasings was wired to each leaf. This
# block adds the agent-noun (-er/-ers), singular/plural, and common-synonym
# forms for EVERY rendering leaf, plus the five leaves that previously had zero
# navigational terms (quick-bites-and-takeout, specialty-food,
# kids-classes-and-camps, colleges-and-higher-ed, vacation-rentals).
#
# Kept as a separate slug -> (terms,) map so the original B.3 map above stays
# readable, then merged with setdefault() so an existing entry always wins (so
# the 2026-06-19 monetization-pass entries above are never overridden — e.g.
# "painters"/"garage door" keep their live slugs). Terms whose leaf is still
# PENDING self-activate when that page ships (resolve_leaf_by_slug -> None).
# ---------------------------------------------------------------------------
_QUERY_TO_LEAF_EXPANSION_2026_06_20: dict[str, tuple[str, ...]] = {
    "accountants-and-tax": ("accountant", "bookkeeper", "bookkeeping", "cpa", "cpas",
        "tax preparation", "tax preparer", "tax service", "tax services"),
    "appliances-and-electronics": ("appliance store", "appliances",
        "electronics", "electronics store"),
    "attorneys": ("attorney", "law firm", "law firms", "law office", "law offices", "lawyer",
        "legal services"),
    "auto-parts": ("auto parts store", "car parts", "napa", "parts store"),
    "auto-repair": ("auto service", "auto shop", "auto shops", "brake repair", "brakes",
        "emissions test", "engine repair", "mechanic", "oil change", "oil changes",
        "smog check", "transmission repair"),
    "bakeries-and-desserts": ("cake shop", "cakes", "cupcakes", "dessert", "desserts",
        "donut shop", "donut shops", "donuts", "doughnuts", "ice cream", "ice cream shop",
        "ice cream shops"),
    "banks-and-credit-unions": ("atm", "bank", "credit union"),
    "bars-and-breweries": ("bar", "beer", "breweries and bars", "brewery", "cocktail bar",
        "cocktail bars", "pub", "pubs", "sports bar", "sports bars", "taproom", "taprooms",
        "wine bar", "wine bars"),
    "beaches-and-swim-areas": ("beach", "public beaches", "swim areas", "swim beach",
        "swimming areas", "swimming beach"),
    "boarding-and-daycare": ("cat boarding", "dog daycare", "dog kennel", "dog kennels",
        "doggy daycare", "pet daycare", "pet hotel"),
    "boat-and-rv-storage-service": ("covered rv storage",),
    "boat-and-watercraft-rentals": ("boat rental companies", "pontoon boat rental",
        "pontoon rental", "pontoon rentals", "watercraft rental"),
    "boat-repair-and-service": ("boat mechanic", "boat motor repair", "boat service",
        "marine repair", "outboard repair"),
    "boat-sales": ("boat dealer", "boat dealership", "boats for sale"),
    "boat-tours-and-charters": ("boat charter", "boat charters", "boat cruises", "boat tour",
        "lake tour", "lake tours", "sunset cruise", "sunset cruises"),
    "cafes-and-coffee": ("cafe", "coffee house", "coffee houses", "coffee shop", "coffeehouse",
        "espresso"),
    "car-dealerships": ("auto dealer", "auto dealers", "car dealership", "car lot", "new cars",
        "used car dealer", "used cars"),
    "car-rental": ("car rental", "rent a car", "rental cars"),
    "car-wash": ("auto wash", "detail wash"),
    "casinos-and-gaming": ("gaming", "slot machines"),
    "chiropractic": ("chiro", "chiropractic care"),
    "cleaning": ("carpet cleaner", "carpet cleaners", "carpet cleaning", "cleaning service",
        "house cleaner", "house cleaners", "janitorial", "maid service", "maid services",
        "window cleaners", "window cleaning"),
    "clothing-and-apparel": ("apparel", "boutique clothing", "clothes", "clothing",
        "clothing store", "mens clothing", "womens clothing"),
    "colleges-and-higher-ed": ("college", "colleges", "community college", "higher education",
        "trade school", "universities", "university"),
    "community-centers": ("community center", "rec center", "recreation center", "senior center"),
    "computer-and-it-repair": ("computer repair shop", "computer service", "it services",
        "laptop repair", "pc repair", "tech support", "virus removal"),
    "convenience": ("convenience store", "corner store", "mini mart"),
    "dance-studios": ("ballet", "ballet classes", "dance classes", "dance lessons",
        "dance studio"),
    "day-spas-and-massage": ("day spa", "facials", "massage therapist", "massage therapists",
        "massage therapy", "masseuse", "spa"),
    "dentists-and-orthodontists": ("cosmetic dentist", "dental", "dental clinic",
        "dental office", "dental offices", "orthodontist", "teeth cleaning"),
    "dermatology-and-skin": ("dermatology", "skin care clinic", "skin doctor"),
    "disc-golf": ("disc golf course", "frisbee golf"),
    "dog-parks": ("dog park", "off leash park"),
    "electrical": ("electric", "electrical contractor", "electrical contractors"),
    "event-planning": ("event planner", "event planning services", "party planner",
        "party planners", "wedding planner"),
    "eye-care": ("eye doctor", "eye doctors", "eye exam", "optician", "opticians",
        "optometrist", "vision center"),
    "family-fun-and-arcades": ("arcade games", "family fun", "fun for kids", "go karts",
        "laser tag", "mini golf"),
    "financial-advisors": ("financial planner", "financial planners", "investment advisor",
        "retirement planning", "wealth management"),
    "fishing-charters-and-guides": ("fishing charter", "fishing guide", "fishing guides",
        "fishing tours", "fishing trips", "guided fishing"),
    "florists": ("floral", "florist", "flower shop", "flowers"),
    "food-trucks-and-catering": ("caterer", "caterers", "catering companies", "food truck"),
    "furniture-and-mattress": ("furniture", "furniture store", "mattress", "mattress store",
        "mattress stores", "mattresses"),
    "gas-stations": ("gas station",),
    "general-contractors": ("builders", "construction companies", "construction company",
        "contractor", "general contractor", "home builder", "home builders", "home remodeling",
        "remodeler", "remodelers", "remodeling"),
    "gifts-and-boutiques": ("boutique", "gift shop", "gifts", "souvenir shop", "souvenirs"),
    "golf-courses": ("driving range", "driving ranges", "golf club", "golf clubs", "golf course"),
    "government-and-mvd": ("city hall", "county office", "courthouse", "dmv office",
        "government office", "motor vehicle"),
    "grocery-and-markets": ("food market", "food stores", "grocery", "grocery store", "markets",
        "supermarket", "supermarkets"),
    "grooming": ("cat grooming", "mobile dog grooming", "mobile pet grooming"),
    "gyms-and-fitness-centers": ("crossfit", "fitness", "fitness center", "fitness club",
        "gym memberships", "health club", "health clubs", "weight training"),
    "hair-salons-and-barbers": ("barber shop", "barber shops", "barbershop", "blowout",
        "hair stylist", "hair stylists", "hairdresser", "hairdressers"),
    "handyman": ("handyman service", "handyman services", "odd jobs"),
    "hardware-and-home-improvement": ("hardware", "hardware store", "home improvement",
        "home improvement store", "lumber"),
    "hiking-trails": ("hike", "hikes", "hiking trail", "nature trails", "trail", "trails",
        "walking trails"),
    "hobby-and-craft": ("art supplies", "art supply store", "craft store", "crafts",
        "fabric store", "hobby shop", "hobby stores"),
    "hotels-and-motels": ("bed and breakfast", "inn", "inns", "motel", "resort", "resorts"),
    "hvac": ("ac installation", "ac service", "air conditioner repair",
        "air conditioning repair", "furnace repair", "heating", "heating and cooling",
        "hvac companies", "hvac repair"),
    "insurance": ("auto insurance", "health insurance", "home insurance", "insurance agency",
        "insurance agent", "insurance broker", "insurance companies"),
    "jet-ski-and-watersports": ("jet ski", "jet ski rental", "sea doo", "seadoo",
        "water sports", "watersports", "wave runner", "wave runners", "waverunner",
        "waverunners"),
    "jewelry": ("jeweler", "jewellery", "jewelry repair", "jewelry store", "watch repair"),
    "k-12-schools": ("charter school", "elementary school", "high school", "middle school",
        "private school", "school"),
    "kayak-and-paddle": ("canoe", "canoe rental", "canoes", "kayak", "kayak rental",
        "paddle board", "paddle boards", "paddleboard", "paddleboarding",
        "stand up paddleboard", "sup rental"),
    "kids-classes-and-camps": ("after school programs", "day camp", "day camps",
        "kids activities", "kids camps", "kids classes", "kids programs", "summer camp",
        "summer camps", "youth programs"),
    "landmarks-and-sights": ("landmark", "points of interest", "scenic spots", "sights"),
    "landscaping-and-lawn": ("gardener", "gardeners", "irrigation", "landscaper",
        "lawn maintenance", "lawn mowing", "lawn service", "lawn services", "sprinkler repair",
        "tree removal", "tree service", "tree trimming", "yard work"),
    "libraries": ("library", "public library"),
    "marinas-and-launch-ramps": ("boat launch", "boat launches", "boat ramp", "boat ramps",
        "launch ramp", "launch ramps", "marina"),
    "martial-arts": ("bjj", "dojo", "jiu jitsu", "karate classes", "kickboxing", "mma",
        "self defense", "taekwondo"),
    "med-spas-and-aesthetics": ("aesthetics", "botox", "fillers", "laser hair removal",
        "medical spa"),
    "mental-and-behavioral-health": ("behavioral health", "counseling", "counselor",
        "psychiatrist", "psychiatrists", "psychologist", "psychologists", "therapist", "therapy"),
    "movers": ("local movers", "moving company", "moving services", "relocation"),
    "museums-and-galleries": ("art galleries", "art gallery", "galleries", "museum"),
    "music-lessons": ("guitar lessons", "music lesson", "music school", "music teacher",
        "piano lessons", "singing lessons"),
    "nail-salons": ("manicure", "manicures", "nail salon", "nail spa", "nail tech", "pedicure",
        "pedicures"),
    "nonprofits-and-charities": ("charitable organizations", "charity", "food bank",
        "non profit", "nonprofit"),
    "nutrition-and-wellness": ("dietician", "dietitian", "nutritionist", "wellness center"),
    "off-road-and-ohv": ("atv trail", "off road", "off road trail", "off roading trails",
        "offroad", "ohv trails", "utv trail"),
    "parks-and-playgrounds": ("city parks", "park", "playground", "playgrounds", "public parks"),
    "personal-training": ("fitness trainer", "fitness trainers"),
    "pest-control": ("bug control", "exterminator", "pest control companies", "termite control"),
    "pet-sitting": ("cat sitter", "cat sitting", "dog sitter", "dog sitting", "dog walker",
        "dog walkers", "dog walking", "pet sitter"),
    "pet-stores-and-supplies": ("aquarium store", "dog food", "pet shop", "pet shops",
        "pet supplies"),
    "pharmacies": ("drug store", "drug stores", "drugstore", "drugstores"),
    "photographers": ("photo studio", "photographer", "photography", "photography studio",
        "portrait photographer", "wedding photographer"),
    "physical-therapy": ("physical therapists", "pt clinic", "rehab", "rehabilitation"),
    "places-of-worship": ("chapel", "church", "mosque", "place of worship", "synagogue",
        "temple"),
    "plumbing": ("drain cleaners", "drain cleaning", "water heater repair"),
    "pools-and-spas": ("hot tub", "hot tub repair", "hot tubs", "pool builder", "pool builders",
        "pool cleaner", "pool cleaners", "pool companies", "pool company", "pool contractor",
        "pool contractors", "pool installation", "pool maintenance", "pool repair",
        "pool resurfacing", "pool servicing", "pool tech", "pool techs", "spa repair",
        "swimming pool", "swimming pools"),
    "powersports-and-atv": ("atv", "atv rental", "dirt bikes", "ohv rentals", "side by side",
        "side by sides", "utv", "utv rental"),
    "preschools-and-childcare": ("child care", "day care", "daycares", "preschool"),
    "primary-care": ("doctor", "family doctor", "family physician", "general practitioner",
        "medical clinic", "medical clinics", "physicians", "primary care doctor",
        "primary care physician"),
    "print-signs-and-marketing": ("banners", "graphic design", "marketing agency", "printer",
        "printers", "sign maker", "sign makers", "signs"),
    "quick-bites-and-takeout": ("burger joint", "burgers", "deli", "delis", "drive thru",
        "fast food", "fast food restaurants", "hot dogs", "pizza", "pizza places", "pizzeria",
        "quick bites", "sandwich shop", "sandwich shops", "sandwiches", "subs", "taco shop",
        "tacos", "take out", "takeout", "wings"),
    "real-estate": ("property listings", "real estate agency", "real estate agent",
        "real estate offices", "realtor"),
    "restaurants": ("dining", "dinner", "family restaurants", "fine dining", "food", "lunch"),
    "roofing": ("roof repair", "roof replacement", "roofing companies", "roofing contractor",
        "roofing contractors"),
    "rv-parks-and-campgrounds": ("campground", "camping", "rv park", "rv resort", "rv resorts"),
    "rv-sales-and-service": ("motorhome repair", "rv dealer", "rv dealership", "rv parts",
        "rv repair shop"),
    "security-and-alarms": ("alarm company", "alarm system", "alarm systems", "home security",
        "security cameras", "security system"),
    "self-storage": ("mini storage", "storage", "storage facilities", "storage facility",
        "storage unit"),
    "senior-care-and-assisted-living": ("assisted living facilities", "independent living",
        "memory care", "nursing home", "retirement home"),
    "shipping-and-postal": ("fedex", "mailbox", "mailboxes", "pack and ship", "postal services",
        "shipping store", "ups store"),
    "shoes": ("shoe store", "shoes", "sneakers"),
    "shuttles-and-transportation": ("airport shuttle", "airport shuttles", "rideshare",
        "shuttle", "taxi", "taxi service", "transportation services"),
    "solar": ("solar companies", "solar company", "solar installer", "solar panel installation",
        "solar panels"),
    "specialty-food": ("butcher", "butcher shop", "candy store", "chocolate shop",
        "farmers market", "gourmet food", "health food store", "specialty food", "spice shop"),
    "sporting-goods": ("fishing gear", "sporting goods store", "sporting goods stores",
        "sports equipment", "sports store"),
    "tanning": ("spray tan", "spray tanning", "tanning salon", "tanning salons"),
    "tattoo-and-piercing": ("body piercing", "piercing", "piercings", "tattoo artist",
        "tattoo artists", "tattoo parlor", "tattoo parlors", "tattoo shop", "tattoos"),
    "theaters-and-cinema": ("movie theater", "movie times", "movies", "theater", "theatre",
        "theatres"),
    "thrift-and-consignment": ("consignment", "consignment shop", "second hand store",
        "thrift shop", "thrift shops", "thrift store"),
    "tires": ("new tires", "tire", "tire repair", "tire shop", "tire store", "tire stores"),
    "tours-and-sightseeing": ("attractions", "sightseeing tours", "things to see", "tour"),
    "towing-and-roadside": ("roadside assistance", "tow service", "tow truck", "towing service",
        "towing services", "wrecker"),
    "training": ("dog obedience", "dog training classes", "obedience training", "puppy training"),
    "tutoring-and-test-prep": ("math tutor", "reading tutor", "sat prep", "test prep", "tutor"),
    "urgent-care-and-er": ("emergency room", "immediate care"),
    "utilities": ("electric company", "power company", "trash service", "utility",
        "water company"),
    "vacation-rentals": ("cabin rentals", "rental homes", "short term rental",
        "short term rentals", "vacation homes", "vacation rental"),
    "veterinarians": ("animal clinic", "animal hospital", "animal hospitals", "vet clinic",
        "vet clinics", "veterinary", "veterinary clinic"),
    "yoga-and-pilates": ("hot yoga", "pilates classes", "pilates studio", "yoga classes",
        "yoga studio", "yoga studios"),
}

# Bare single-word forms that still dead-ended on an EXISTING page (the noun
# alone is a natural search, but only multi-word phrasings were mapped above).
_QUERY_TO_LEAF_BARE_FORMS_2026_06_20: dict[str, str] = {
    "cleaning": "cleaning",
    "jewelry": "jewelry",
    "pool": "pools-and-spas",
    "pools": "pools-and-spas",
    "appliance": "appliances-and-electronics",
    "smoke shop": "smoke-vape-and-cannabis",
    "vape": "smoke-vape-and-cannabis",
    "vape shop": "smoke-vape-and-cannabis",
}

# Routing for the BRAND-NEW leaves (slugs added to PENDING_LEAF_SLUGS above).
# No-ops until scripts/create_missing_service_leaves_2026_06_20.py seeds the leaf
# and it clears the leaf_pages.LEAF_PAGE_MIN_PROVIDERS publish gate (via
# _resolve_gated); then these searches start landing on the page.
# NOTE: "painters" and "garage-doors" are already LIVE (2026-06-19 pass), so
# their extra agent-noun/synonym forms below route to the existing live page via
# setdefault — they are not pending.
_QUERY_TO_LEAF_NEW_LEAVES_2026_06_20: dict[str, tuple[str, ...]] = {
    "painters": ("painter", "painters", "painting", "painting contractor",
        "painting contractors", "paint contractor", "house painter", "house painters",
        "house painting", "interior painting", "exterior painting", "commercial painting"),
    "locksmiths": ("locksmith", "locksmiths", "lockout service", "rekey", "re key",
        "lock repair", "lock installation", "key duplication", "car key replacement"),
    # 2026-06-20 batch 2
    "flooring": ("flooring", "flooring store", "flooring contractor", "flooring contractors",
        "floor installation", "floor installer", "floor installers", "carpet installation",
        "tile installation", "hardwood flooring", "laminate flooring", "vinyl plank"),
    "fencing": ("fencing", "fence company", "fence companies", "fence contractor",
        "fence contractors", "fence installation", "fence repair", "fence builder",
        "fencing company", "wrought iron fence", "chain link fence"),
    "garage-doors": ("garage door", "garage doors", "garage door repair",
        "garage door installation", "garage door opener", "garage door service",
        "overhead door", "overhead doors"),
    "concrete-and-masonry": ("concrete", "concrete contractor", "concrete contractors",
        "concrete driveway", "decorative concrete", "stamped concrete", "masonry", "mason",
        "masons", "block wall", "block walls", "retaining wall", "retaining walls", "pavers",
        "paver installation", "stucco", "rv pad", "rv pads"),
    # 2026-06-20 batch 3 — brand-new leaves
    "drywall": ("drywall", "drywall repair", "drywall contractor", "drywall contractors",
        "drywall installation", "sheetrock"),
    "carpentry-and-cabinets": ("carpenter", "carpenters", "carpentry", "custom cabinets",
        "cabinet maker", "cabinet makers", "cabinets", "kitchen cabinets", "cabinet refacing",
        "finish carpentry", "woodworking"),
    "welding-and-fabrication": ("welder", "welders", "welding", "welding shop",
        "metal fabrication", "fabrication", "fabricator", "metal fabricators", "mobile welding"),
    "gutters": ("gutter", "gutters", "gutter installation", "gutter repair", "seamless gutters",
        "rain gutters", "gutter company"),
    # Bare "windows" routes here (not the auto window-tint leaf): "window tint"/
    # "window tinting" are distinct exact keys and share no token with the plural
    # "windows", so the more-specific tint match still wins.
    "windows-and-doors": ("windows", "window installation", "window replacement",
        "replacement windows", "window installer", "door installation", "door installer",
        "windows and doors", "new windows", "patio doors", "sliding doors"),
    "appliance-repair": ("appliance repair", "appliance repairman", "appliance service",
        "refrigerator repair", "washer repair", "dryer repair", "dishwasher repair",
        "oven repair", "stove repair", "freezer repair"),
    "liquor-stores": ("liquor store", "liquor stores", "liquor", "package store",
        "beer and wine", "wine and spirits"),
    "pawn-shops": ("pawn shop", "pawn shops", "pawnshop", "pawn", "pawnbroker", "pawn broker"),
    "nurseries-and-garden-centers": ("nursery", "plant nursery", "garden center",
        "garden centers", "nurseries", "garden nursery", "plant store"),
    # 2026-06-20 batch 3 — enrichment for already-designed (pending) leaves; in
    # particular medical-specialists-and-imaging previously had NO search terms.
    "medical-specialists-and-imaging": ("imaging", "imaging center", "medical imaging",
        "radiology", "mri", "ct scan", "x ray", "ultrasound", "specialists",
        "medical specialists", "cardiologist", "cardiologists", "neurologist", "orthopedic",
        "oncologist", "podiatrist", "urologist", "ear nose and throat"),
    "firearms-and-shooting-sports": ("gun store", "gun shop", "shooting sports", "gunsmith",
        "ammo", "guns and ammo"),
    "trailer-sales-and-repair": ("trailer dealer", "utility trailer", "trailer parts"),
    "mobile-home-services": ("manufactured home repair", "mobile home service"),
    "shade-screens-and-patio-covers": ("patio cover", "sun screen", "awning",
        "retractable awning", "sun shades", "solar screens"),
    "pet-waste-removal": ("dog poop removal", "poop scooping", "dog waste removal"),
}

# 2026-06-28 intent-search alias pass (directory-audit §11). Each entry is a
# category NOUN/phrase — NEVER a descriptive sentence (those stay conversational
# by design; see test_leaf_query.test_normalize_leaves_descriptive_queries_unmatched)
# — routing to an ALREADY-POPULATED leaf, closing the live-search gaps surfaced by
# scripts/audit_search_intent_coverage_2026_06_28.py. These reach the keyword search
# via the leaf-link bridge (app.search.routes._leaf_link_exists_predicate); a term
# pointing at a sub-gate/empty leaf is a harmless no-op until it's seeded.
_QUERY_TO_LEAF_SEARCH_ALIASES_2026_06_28: dict[str, tuple[str, ...]] = {
    "hvac": ("swamp cooler", "swamp coolers", "swamp cooler repair", "evaporative cooler",
        "evaporative coolers", "mini split", "ductless mini split", "ac install",
        "ac installation", "ac tune up", "new ac unit", "ac unit"),
    "roofing": ("leaky roof", "roof leak", "roof leak repair"),
    "pest-control": ("bug guy", "bug man"),
    "plumbing": ("water heater", "water heaters", "water heater repair",
        "water heater installation", "water heater replacement", "tankless water heater"),
    "title-and-escrow": ("title company", "title companies", "escrow company"),
    "pools-and-spas": ("pool pump", "pool pumps", "pool equipment", "pool filter"),
    "vacation-rentals": ("airbnb", "air bnb", "vrbo", "short term rental",
        "short term rentals", "vacation home", "vacation homes"),
    "veterinarians": ("emergency vet", "emergency veterinarian", "24 hour vet", "24 hr vet"),
    "utilities": ("trash pickup", "trash service", "garbage pickup", "garbage service",
        "recycling", "recycling center", "water company", "electric company",
        "power company", "gas company"),
    "gifts-and-boutiques": ("gift shops", "gift store", "gift stores"),
    # ("pediatrician" et al. pointed here 2026-06-28 as a stopgap; moved to the
    # dedicated ``pediatrics`` leaf in the 2026-07-01 dict below — the 159-row
    # primary-care dump was the audit's A2 complaint.)
}

# 2026-06-30 search-audit expansion (ASKHAVA_SEARCH_AUDIT_2026-06-30 §A3 / PART
# D). The leaf exists and is populated, but these phrasings were never wired, so
# the box dropped to a weak conversational answer instead of the page (e.g.
# "kayak rentals" reached the leaf but "paddleboard rentals" didn't). Same
# mechanism as the 2026-06-20 pool-builders pass: category NOUNS only (never a
# descriptive sentence), merged via setdefault so any live entry above wins.
# Attraction terms (escape room, axe throwing, trampoline park...) point at the
# existing Things-to-Do leaves so they land on a real page now, and become exact
# once Phase 2 backfills VR Escape Reality / the helicopter operators.
# NB: "scenic flight" is deliberately NOT added -- its token "flight" is one edit
# from the common word "light" ("light switch not working") and would pollute the
# shared spell-correct vocab (normalizer._spell_vocab). "helicopter tour(s)" is
# distinctive and covers the same intent without that footgun.
_QUERY_TO_LEAF_SEARCH_ADD_2026_06_30: dict[str, tuple[str, ...]] = {
    "kayak-and-paddle": ("paddleboard rentals", "paddle board rental"),
    "jet-ski-and-watersports": ("wake surfing", "wakesurf", "wakesurfing",
        "wakeboarding", "flyboard"),
    "fishing-charters-and-guides": ("fishing trip", "bass fishing guide"),
    "music-lessons": ("drum lessons",),
    "family-fun-and-arcades": ("escape room", "escape rooms", "axe throwing",
        "miniature golf", "trampoline park"),
    "tours-and-sightseeing": ("helicopter tour", "helicopter tours"),
}

# 2026-06-30 follow-on: the data backfill added Havasu Parasail (jet-ski leaf)
# and created the scuba-and-dive leaf (re-homing Scuba Training & Technology off
# jet-ski-and-watersports). Wire the phrasings that reach them. "scuba-and-dive"
# is a real live leaf (added to docs/proposals/taxonomy-seed.json) so the drift
# guard passes.
_QUERY_TO_LEAF_SEARCH_ADD2_2026_06_30: dict[str, tuple[str, ...]] = {
    "jet-ski-and-watersports": ("parasailing", "parasail"),
    "scuba-and-dive": ("scuba", "scuba diving", "scuba lessons", "scuba certification",
        "dive shop", "dive shops", "scuba shop"),
}

# 2026-07-01 consolidated search audit (A3 + A5). The calendar router no longer
# captures these evergreen asks (is_discovery_query is scoped to explicit
# time/event intent), so each gets a real directory destination; plus the
# bare/variant terms the audit found unmapped ("hair" -> the 83-listing salons
# leaf, phone-repair variants -> the IT-repair leaf). Category NOUNS only
# (never a descriptive sentence), merged via setdefault so live entries win.
_QUERY_TO_LEAF_SEARCH_ADD_2026_07_01: dict[str, tuple[str, ...]] = {
    "bars-and-breweries": ("nightlife", "happy hour"),
    "restaurants": ("date night", "waterfront dining"),
    # "lake havasu state park" normalizes to "state park" (the locality filler
    # strip removes "lake havasu" first); the park's beach rows live on the
    # beaches leaf.
    "beaches-and-swim-areas": ("state park", "state parks"),
    "boat-and-watercraft-rentals": ("party boat", "party boats",
        "party boat rental", "party boat rentals"),
    "boat-tours-and-charters": ("boat rental with captain", "captained boat tour",
        "captained boat tours"),
    "hair-salons-and-barbers": ("hair",),
    "computer-and-it-repair": ("cell phone repair", "phone repair",
        "iphone repair", "phone screen repair"),
    "jet-ski-and-watersports": ("waverunner rental", "waverunner rentals",
        "sea doo rental", "sea doo rentals"),
    # A2: the missing specialty terms. medical-specialists-and-imaging already
    # carries cardiologist/podiatrist/etc. (2026-06-20 block above) and
    # self-activates when the Phase-3 data op seeds the leaf; these add the
    # obgyn family and the lab terms (which also ends the "lab" → Fit Lab 928
    # gym collision — the gym row is correctly categorized and stays put).
    # "women s health" is the _normalize output of "women's health".
    "medical-specialists-and-imaging": ("obgyn", "ob gyn", "obstetrician",
        "gynecologist", "womens health", "women s health",
        "lab", "labs", "medical lab", "medical labs", "blood work", "lab work"),
    # Pediatricians get their own leaf (seeded in Phase 3; a deliberate no-op
    # until then per _resolve_gated) instead of the 159-doctor primary-care leaf.
    "pediatrics": ("pediatrician", "pediatricians", "pediatrics"),
    # Master site audit §1 (2026-07-01 PM): "pool supply" had no route to the
    # 15-listing pools leaf ("pool", "pool service", "pool pump" etc. were all
    # wired; the supply/store phrasings weren't) — it fell to chat and, for
    # "pool store", the bare "store" token bought the shopping junk fallback.
    "pools-and-spas": ("pool supply", "pool supplies", "pool store", "pool stores"),
}

# Evergreen browse asks whose right destination is a DEPARTMENT landing or a
# static page, not a single leaf (the dicts above can only target leaf slugs).
# Consulted by the /chat router ahead of the leaf match via
# :func:`match_direct_destination`; these routes always render, so no publish
# gate applies. "things to do" -> the Things to Do department landing (a real
# browse page; the tours-and-sightseeing leaf is too narrow for the ask);
# the kids variant -> the /family day view.
_QUERY_TO_URL_2026_07_01: dict[str, str] = {
    "things to do": "/categories/things-to-do-and-attractions",
    "fun things to do": "/categories/things-to-do-and-attractions",
    "free things to do": "/categories/things-to-do-and-attractions",
    "stuff to do": "/categories/things-to-do-and-attractions",
    "things to do with kids": "/family",
}


def match_direct_destination(q: str | None) -> str | None:
    """Static destination URL for an evergreen browse ask, or ``None``.

    Pure in-memory lookup on the normalized query -- no DB, because the
    department landing and /family always render (unlike leaf pages, which
    carry the publish gate)."""
    norm = _normalize(q or "")
    if not norm:
        return None
    return _QUERY_TO_URL_2026_07_01.get(norm)


for _leaf_slug, _terms in _QUERY_TO_LEAF_EXPANSION_2026_06_20.items():
    for _term in _terms:
        _QUERY_TO_LEAF.setdefault(_term, _leaf_slug)
for _leaf_slug, _terms in _QUERY_TO_LEAF_NEW_LEAVES_2026_06_20.items():
    for _term in _terms:
        _QUERY_TO_LEAF.setdefault(_term, _leaf_slug)
for _leaf_slug, _terms in _QUERY_TO_LEAF_SEARCH_ALIASES_2026_06_28.items():
    for _term in _terms:
        _QUERY_TO_LEAF.setdefault(_term, _leaf_slug)
for _leaf_slug, _terms in _QUERY_TO_LEAF_SEARCH_ADD_2026_06_30.items():
    for _term in _terms:
        _QUERY_TO_LEAF.setdefault(_term, _leaf_slug)
for _leaf_slug, _terms in _QUERY_TO_LEAF_SEARCH_ADD2_2026_06_30.items():
    for _term in _terms:
        _QUERY_TO_LEAF.setdefault(_term, _leaf_slug)
for _leaf_slug, _terms in _QUERY_TO_LEAF_SEARCH_ADD_2026_07_01.items():
    for _term in _terms:
        _QUERY_TO_LEAF.setdefault(_term, _leaf_slug)
for _term, _leaf_slug in _QUERY_TO_LEAF_BARE_FORMS_2026_06_20.items():
    _QUERY_TO_LEAF.setdefault(_term, _leaf_slug)


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

# Service-intent + function words that can surround a category noun in a
# need-shaped query ("hvac needs repair", "pool service repair", "coffee shop").
# match_leaf_service_intent routes such a query to its leaf ONLY when, after
# pulling out a single category keyword, every remaining token is in this set —
# so a descriptive ask carrying a content word ("wifi password coffee shop",
# "best plumber for a slab leak") still falls through. Deliberately holds NO
# category nouns and NO factual/temporal words (those are _CONVERSATIONAL_TOKENS).
_SERVICE_FILLER: frozenset[str] = frozenset(
    {
        # service intent
        "repair", "repairs", "service", "services", "servicing", "need", "needs",
        "needed", "broken", "fix", "fixing", "fixed", "install", "installation",
        "installer", "installers", "replace", "replacement", "maintenance", "help",
        "quote", "quotes", "estimate", "estimates", "recommendation", "recommendations",
        "company", "companies", "guy", "guys", "shop", "shops", "place", "places",
        "unit", "units", "get", "find", "hire", "book",
        # 2026-07-01: rent-intent words, so "<mapped-category> rental" routes
        # ("waverunner rental", "pontoon boat rental"). "golf cart rental" stays
        # safely unrouted -- its leftover "cart" is a content token.
        "rent", "rents", "rental", "rentals", "renting",
        # breakdown phrasings ("my hvac is broken", "ac not working", "stopped")
        "is", "are", "was", "broke", "not", "working", "stopped",
        # harmless function words (no category signal)
        "i", "we", "my", "a", "an", "the", "for", "to", "some", "any", "please",
        "looking", "near", "around", "local", "and", "of",
    }
)


def _has_conversational_payload(raw: str) -> bool:
    """True when the RAW query carries factual/temporal payload (hours, phone,
    "open now", "tonight"…) — those stay conversational and never service-route.
    Checked on the raw text BEFORE _normalize, which strips some of these."""
    return any(tok in raw for tok in _CONVERSATIONAL_TOKENS)


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


def _resolve_gated(db: Session, slug: str) -> leaf_pages.Leaf | None:
    """DB existence + thin-page (≥3-provider) gate for a known leaf slug."""
    leaf = leaf_pages.resolve_leaf_by_slug(db, slug)
    if leaf is None:
        return None
    if leaf_pages.leaf_renderable_count(db, leaf) < leaf_pages.LEAF_PAGE_MIN_PROVIDERS:
        return None
    return leaf


def _leaf_for_normalized_term(db: Session, norm: str) -> leaf_pages.Leaf | None:
    """Dict lookup + DB existence + thin-page gate for a normalized term."""
    slug = _QUERY_TO_LEAF.get(norm)
    if slug is None:
        return None
    return _resolve_gated(db, slug)


def _service_intent_slug(norm: str) -> str | None:
    """A single unambiguous leaf slug a need-shaped query maps to, or ``None``.

    Pure (no DB). Finds known navigational terms as contiguous token spans in
    the normalized query, longest-span-per-start. Routes ONLY when every span
    resolves to ONE leaf AND every leftover token is service/function filler —
    so "hvac needs repair" → ``hvac`` but "wifi password coffee shop" (content
    leftover) and "plumber and electrician" (two leaves) fall through.
    """
    toks = norm.split()
    if len(toks) < 2:
        return None  # single-token asks are the exact-match path's job
    n = len(toks)
    spans: list[tuple[int, int, str]] = []
    for i in range(n):
        for j in range(n, i, -1):  # longest span starting at i wins
            slug = _QUERY_TO_LEAF.get(" ".join(toks[i:j]))
            if slug is not None:
                spans.append((i, j, slug))
                break
    if not spans:
        return None
    slugs = {s for _, _, s in spans}
    if len(slugs) != 1:
        return None  # ambiguous — multiple categories implied
    covered: set[int] = set()
    for i, j, _ in spans:
        covered.update(range(i, j))
    leftover = [toks[k] for k in range(n) if k not in covered]
    if any(t not in _SERVICE_FILLER for t in leftover):
        return None  # a content word remains → stay conservative, fall through
    return next(iter(slugs))


def match_leaf_service_intent(db: Session, q: str | None) -> leaf_pages.Leaf | None:
    """Leaf match for need-shaped service queries the exact matcher misses.

    Extends :func:`match_leaf_query`: routes "[category] + service/function
    words" ("hvac needs repair", "pool service repair", "coffee shop") to the
    leaf, while queries with factual/temporal payload or any content leftover
    stay conversational. The candidate leaf must still clear the existence +
    ≥3-provider gate. Used as the fall-through before /search in the concierge.
    """
    raw = (q or "").strip().lower()
    if not raw or _has_conversational_payload(raw):
        return None
    slug = _service_intent_slug(_normalize(raw))
    if slug is None:
        return None
    return _resolve_gated(db, slug)
