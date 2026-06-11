"""2026-06-11 dictionary expansion — routing + zero-collision regression.

The expansion is safe by construction (the intent layer falls through on zero
rows), but the RESOLVER must still send each new term to the right intent and
must NOT let a new key hijack a phrase an older branch already owned.
"""

from __future__ import annotations

import pytest

from app.chat.intents import dicts
from app.chat.intents.resolver import resolve

# ---------------------------------------------------------------------------
# New service terms route to find_service with the right slot.
# ---------------------------------------------------------------------------

SERVICE_CASES = [
    ("i need a tow truck", "tow truck"),
    ("towing in lake havasu", "towing"),
    ("auto glass shop", "auto glass"),
    ("windshield replacement", "windshield replacement"),
    ("window tint place", "window tint"),
    ("vehicle wraps", "vehicle wraps"),
    ("who does car wraps in town", "car wraps"),
    ("mobile detailing", "mobile detailing"),
    ("auto detailing", "auto detailing"),
    ("golf cart repair", "golf cart repair"),
    ("any good locksmith", "locksmith"),
    ("appliance repair", "appliance repair"),
    ("garage door repair", "garage door repair"),
    ("tree trimming service", "tree trimming"),
    ("junk removal", "junk removal"),
    ("pressure washing", "pressure washing"),
    ("septic pumping", "septic pumping"),
    ("property management company", "property management"),
    ("laundromat", "laundromat"),
    ("dry cleaner", "dry cleaner"),
    ("notary", "notary"),
    ("computer repair shop", "computer repair"),
    ("phone repair", "phone repair"),
    ("sign shop", "sign shop"),
    ("event planner", "event planner"),
    ("wedding planner", "wedding planner"),
    ("pet sitter", "pet sitter"),
    ("dog walker", "dog walker"),
    ("pooper scooper service", "pooper scooper"),
    ("hearing aids", "hearing aids"),
    ("audiologist", "audiologist"),
    ("dermatologist", "dermatologist"),
    ("mental health counselor", "mental health"),
    ("funeral home", "funeral home"),
    ("cremation", "cremation"),
    ("tattoo shop", "tattoo shop"),
    ("med spa", "med spa"),
    ("movers", "movers"),
    ("solar installer", "solar installer"),
    ("boat storage", "boat storage"),
    ("rv storage", "rv storage"),
    ("trailer repair", "trailer repair"),
    ("home inspector", "home inspector"),
    ("propane refill", "propane"),
]


@pytest.mark.parametrize("query,service", SERVICE_CASES, ids=[c[0] for c in SERVICE_CASES])
def test_new_service_terms_route(query, service):
    resolved = resolve(query)
    assert resolved is not None, f"{query!r} fell through"
    assert resolved.intent_key == "find_service", f"{query!r} -> {resolved.intent_key}"
    assert resolved.slots.get("service") == service


def test_all_routes_use_real_subcat_groups():
    for term, route in dicts.SERVICE_DICT.items():
        assert route.subcat in dicts.SERVICE_SUBCAT_GROUPS, (term, route.subcat)
        assert route.name_tokens, term


# ---------------------------------------------------------------------------
# New cuisines.
# ---------------------------------------------------------------------------

CUISINE_CASES = [
    ("best wings in town", "wings"),
    ("sandwich shop", "sandwich"),
    ("ice cream for the kids", "ice cream"),
    ("donuts", "donuts"),
    ("greek food", "greek"),
    ("pho", "pho"),
    ("poke bowl", "poke"),
    ("wine bar", "wine bar"),
    ("sports bar", "sports bar"),
    ("vegan options", "vegan"),
    ("smoothies", "smoothies"),
    ("food trucks", None),  # event-words guard: "food trucks" must stay eat-routed
]


@pytest.mark.parametrize("query,cuisine", CUISINE_CASES, ids=[c[0] for c in CUISINE_CASES])
def test_new_cuisines_route_to_eat(query, cuisine):
    resolved = resolve(query)
    assert resolved is not None, f"{query!r} fell through"
    assert resolved.intent_key in ("eat_find", "eat_open_now"), (
        f"{query!r} -> {resolved.intent_key}"
    )
    if cuisine is not None:
        assert resolved.slots.get("cuisine") == cuisine


def test_new_symptoms_route_to_urgent_or_listing():
    for q, expected_sub in [
        ("i need stitches", "stitches"),
        ("sprained ankle", "sprained ankle"),
        ("flu shot", "flu shot"),
        ("my tooth hurts", "tooth hurts"),
    ]:
        resolved = resolve(q)
        assert resolved is not None and resolved.intent_key == "urgent_care", q
        assert resolved.slots.get("symptom") == expected_sub


# ---------------------------------------------------------------------------
# Zero-collision regression: phrases older branches own must not move.
# ---------------------------------------------------------------------------

REGRESSION_CASES = [
    # (query, expected_intent) — all routed identically before the expansion.
    ("cheapest gas", "cheapest_gas"),
    ("what is happening this weekend", "events_weekend"),
    ("live music tonight", "events_today"),
    ("i need a plumber", "find_service"),
    ("best mexican food", "eat_find"),
    ("rv park", "lodging_find"),  # NOT rv repair / rv storage
    ("hotels near the lake", "lodging_find"),
    ("rent a boat", "boat_rental"),
    ("boat mechanic in town", "boat_repair"),  # water+repair guard intact
    ("hiking trails", "parks_trails"),
    ("food bank", "civic_resources"),
    ("buy fishing gear", "shopping_find"),
    ("swim lessons for my 8 year old", "kids_lessons"),
    ("yoga classes", "yoga_pilates"),
]


@pytest.mark.parametrize("query,intent", REGRESSION_CASES, ids=[c[0] for c in REGRESSION_CASES])
def test_existing_routing_unchanged(query, intent):
    resolved = resolve(query)
    assert resolved is not None, f"{query!r} fell through"
    assert resolved.intent_key == intent, f"{query!r} -> {resolved.intent_key}"


def test_event_planner_is_service_not_events():
    # 2026-06-11 guard: "event planner" must reach the service dict, not the
    # events listing branch (the "event" token used to hijack it).
    resolved = resolve("event planner")
    assert resolved is not None
    assert resolved.intent_key == "find_service"
    assert resolved.slots.get("service") == "event planner"


def test_sign_up_phrasings_do_not_hit_sign_shop():
    # "sign up for ..." must never read the "sign" as a sign-shop ask. The
    # class branches own it ("daughter" carries no kid-word, so the general
    # classes browse is today's routing; "kids" phrasing gets kids_lessons).
    resolved = resolve("sign up for swim lessons for my daughter")
    assert resolved is not None
    assert resolved.intent_key in ("kids_lessons", "classes_find")
    resolved2 = resolve("sign up for swim lessons for my kids")
    assert resolved2 is not None
    assert resolved2.intent_key == "kids_lessons"


def test_storage_keys_resolve_before_water_branch():
    resolved = resolve("boat storage")
    assert resolved is not None
    assert resolved.intent_key == "find_service"
    assert resolved.slots.get("service") == "boat storage"


def test_new_water_and_park_nouns():
    r1 = resolve("rent a pontoon for the day")
    assert r1 is not None and r1.intent_key == "boat_rental"
    r2 = resolve("playgrounds for toddlers")
    assert r2 is not None and r2.intent_key == "parks_trails"
