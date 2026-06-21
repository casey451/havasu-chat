"""2026-06-20 search-coverage expansion — routing + drift guards (DB-free).

Casey reported that typing plain service terms into Ask Hava ("pool builders",
"pool cleaners", and many others) returned "sorry, no results" instead of the
matching directory page. Root cause: only a narrow set of phrasings was wired
to each leaf in ``_QUERY_TO_LEAF`` — the agent-noun (-er/-ers), some plurals,
and most synonyms were missing, and five rendering leaves had zero navigational
terms at all.

These tests assert the dict + normalizer layer only (no DB). The DB existence /
≥1-provider gate is covered by the existing leaf_query integration tests; an
entry whose leaf is still PENDING is a deliberate runtime no-op until that page
ships (see ``PENDING_LEAF_SLUGS``).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.categories.leaf_query import (
    _QUERY_TO_LEAF,
    _QUERY_TO_LEAF_BARE_FORMS_2026_06_20,
    _QUERY_TO_LEAF_EXPANSION_2026_06_20,
    _QUERY_TO_LEAF_NEW_LEAVES_2026_06_20,
    PENDING_LEAF_SLUGS,
    _normalize,
)

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"


def _live_seed_slugs() -> frozenset[str]:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    slugs: set[str] = set()
    for body in data.values():
        slugs.update((body.get("leaves") or {}).keys())
    return frozenset(slugs)


# --- the exact regression Casey reported ----------------------------------
POOL_CASES = [
    "pool builders",
    "pool builder",
    "pool cleaners",
    "pool cleaner",
    "pool repair",
    "pool contractors",
    "pool maintenance",
    "swimming pool",
    "hot tub repair",
    "best pool builders in lake havasu",
    "pool builders near me",
    "i need a pool builder",  # listing-shaped, handled by match_leaf_for_chat
]


def test_pool_terms_all_route_to_pools_and_spas():
    for raw in POOL_CASES:
        norm = _normalize(raw)
        # the bare navigational term (locality/lead stripping handled by callers)
        # must be present for at least the non-listing phrasings.
        if raw.startswith("i need"):
            continue
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == "pools-and-spas", (raw, norm, _QUERY_TO_LEAF[norm])


# --- broad agent-noun / plural / synonym coverage --------------------------
ROUTING_CASES = {
    # agent nouns & synonyms -> existing leaves
    "roofing contractors": "roofing",
    "house cleaners": "cleaning",
    "carpet cleaning": "cleaning",
    "tree service": "landscaping-and-lawn",
    "lawn service": "landscaping-and-lawn",
    "tow truck": "towing-and-roadside",
    "roadside assistance": "towing-and-roadside",
    "animal hospital": "veterinarians",
    "vet clinic": "veterinarians",
    "dog walker": "pet-sitting",
    "law firm": "attorneys",
    "eye doctor": "eye-care",
    "optometrist": "eye-care",
    "massage therapist": "day-spas-and-massage",
    "barber shop": "hair-salons-and-barbers",
    "drug store": "pharmacies",
    "moving company": "movers",
    "home builders": "general-contractors",
    "solar installer": "solar",
    "ac repair": "hvac",
    "furnace repair": "hvac",
    "mechanic": "auto-repair",
    "oil change": "auto-repair",
    "tire shop": "tires",
    "credit union": "banks-and-credit-unions",
    "wedding photographer": "photographers",
    "personal trainer": "personal-training",
    "yoga studio": "yoga-and-pilates",
    "marina": "marinas-and-launch-ramps",
    "boat ramp": "marinas-and-launch-ramps",
    "kayak rental": "kayak-and-paddle",
    "golf course": "golf-courses",
    "art gallery": "museums-and-galleries",
    # previously-zero-term leaves now reachable
    "quick bites": "quick-bites-and-takeout",
    "takeout": "quick-bites-and-takeout",
    "tacos": "quick-bites-and-takeout",
    "specialty food": "specialty-food",
    "butcher shop": "specialty-food",
    "summer camps": "kids-classes-and-camps",
    "kids activities": "kids-classes-and-camps",
    "college": "colleges-and-higher-ed",
    "university": "colleges-and-higher-ed",
    "vacation rental": "vacation-rentals",
    # bare single-word forms that used to dead-end
    "jewelry": "jewelry",
    "cleaning": "cleaning",
    "pool": "pools-and-spas",
    "pools": "pools-and-spas",
    "vape": "smoke-vape-and-cannabis",
    # painting is already LIVE as the "painters" leaf (2026-06-19 pass) — our
    # extra agent-noun/synonym forms route to that existing page.
    "painters": "painters",
    "house painters": "painters",
    "painting contractors": "painters",
    # brand-new leaves (slugs in PENDING until the page is seeded)
    "locksmith": "locksmiths",
    "lockout service": "locksmiths",
    # batch 2 brand-new leaves
    "flooring": "flooring",
    "floor installation": "flooring",
    "fence company": "fencing",
    "fence contractors": "fencing",
    "garage door repair": "garage-doors",
    "overhead door": "garage-doors",
    "concrete contractor": "concrete-and-masonry",
    "block wall": "concrete-and-masonry",
    # batch 3 brand-new leaves
    "drywall": "drywall",
    "custom cabinets": "carpentry-and-cabinets",
    "cabinet maker": "carpentry-and-cabinets",
    "welder": "welding-and-fabrication",
    "metal fabrication": "welding-and-fabrication",
    "gutter installation": "gutters",
    "replacement windows": "windows-and-doors",
    "appliance repair": "appliance-repair",
    "refrigerator repair": "appliance-repair",
    "liquor store": "liquor-stores",
    "pawn shop": "pawn-shops",
    "garden center": "nurseries-and-garden-centers",
    # batch 3 enrichment of already-designed (pending) leaves
    "imaging center": "medical-specialists-and-imaging",
    "radiology": "medical-specialists-and-imaging",
    "gun store": "firearms-and-shooting-sports",
}


def test_navigational_terms_route_to_expected_leaf():
    for raw, slug in ROUTING_CASES.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


# --- misspelling tolerance (alias map + fuzzy) -----------------------------
MISSPELLING_CASES = {
    "poool builders": "pools-and-spas",
    "matress store": "furniture-and-mattress",
    "jewlery store": "jewelry",
    "appliace repair": "appliance-repair",
    "optomotrist": "eye-care",
    "resteraunt": "restaurants",
    "masage": "day-spas-and-massage",
    "plummbers": "plumbing",       # fuzzy path
    "electricion": "electrical",   # alias path
}


def test_common_misspellings_still_route():
    for raw, slug in MISSPELLING_CASES.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


# --- structural guards -----------------------------------------------------
def test_expansion_targets_are_live_or_pending():
    live = _live_seed_slugs()
    for slug in _QUERY_TO_LEAF_EXPANSION_2026_06_20:
        assert slug in live or slug in PENDING_LEAF_SLUGS, slug
    for slug in _QUERY_TO_LEAF_NEW_LEAVES_2026_06_20:
        assert slug in live or slug in PENDING_LEAF_SLUGS, slug
    for slug in _QUERY_TO_LEAF_BARE_FORMS_2026_06_20.values():
        assert slug in live or slug in PENDING_LEAF_SLUGS, slug


def test_expansion_keys_normalize_to_themselves():
    # Every navigational key must be the OUTPUT of _normalize, else it can never
    # be hit at runtime. Expansion is slug -> (terms,); bare is term -> slug.
    for _mapping in (
        _QUERY_TO_LEAF_EXPANSION_2026_06_20,
        _QUERY_TO_LEAF_NEW_LEAVES_2026_06_20,
    ):
        for _slug, terms in _mapping.items():
            for term in terms:
                assert _normalize(term) == term, (term, _normalize(term))
    for term in _QUERY_TO_LEAF_BARE_FORMS_2026_06_20:
        assert _normalize(term) == term, (term, _normalize(term))


def test_expansion_did_not_override_original_entries():
    # setdefault must preserve any pre-existing mapping; assert a few anchors.
    anchors = {
        "plumbers": "plumbing",
        "boat rentals": "boat-and-watercraft-rentals",
        "med spas": "med-spas-and-aesthetics",
        "massage": "day-spas-and-massage",
        "restaurant": "restaurants",
    }
    for term, slug in anchors.items():
        assert _QUERY_TO_LEAF[term] == slug
