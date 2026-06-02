"""Pure unit tests for the Ask Hava intent resolver (no DB).

Phrase banks -> expected intent + key slots, the master-spec §4.2 age
normalization equivalence, and the conservative fall-through contract.
"""

from __future__ import annotations

import pytest

from app.chat.intents import dicts
from app.chat.intents.resolver import resolve


@pytest.mark.parametrize(
    "query, intent_key",
    [
        ("where's the cheapest gas", "cheapest_gas"),
        ("cheapest gas near me", "cheapest_gas"),
        ("gas prices", "cheapest_gas"),
        ("what events are happening this weekend", "events_weekend"),
        ("things to do tonight", "events_today"),
        ("what's going on next week", "events_next_week"),
        ("any live music this weekend", "events_weekend"),
        ("i need a plumber", "find_service"),
        ("good mechanic in town", "find_service"),
        ("dog groomer", "find_service"),
        ("hair salon", "find_service"),
        ("urgent care", "urgent_care"),
        ("i have a toothache", "urgent_care"),
        ("best mexican food", "eat_find"),
        ("pizza near downtown", "eat_find"),
        ("somewhere to eat open now", "eat_open_now"),
        ("yoga studio", "yoga_pilates"),
        ("gym near me", "gym_fitness"),
        ("karate for my 8 year old", "martial_arts"),
        ("swim lessons for my 8 year old", "kids_lessons"),
        ("hotels near the lake", "lodging_find"),
        ("place to stay this weekend", "lodging_find"),
        ("where can i go shopping", "shopping_find"),
        # On-the-water bucket (Step 1 gap-fix).
        ("where can i rent a boat", "boat_rental"),
        ("kayak rental", "boat_rental"),
        ("jet ski rentals on the lake", "boat_rental"),
        ("boat repair shop", "boat_repair"),
        ("who services boats", "boat_repair"),
        ("where's the boat launch", "on_the_water"),
        ("closest marina", "on_the_water"),
        ("good fishing spots", "on_the_water"),
        # Parks / trails / beaches.
        ("hiking trails near me", "parks_trails"),
        ("best beach in town", "parks_trails"),
        ("where's a good park", "parks_trails"),
        # Civic / community.
        ("where's a church", "civic_resources"),
        ("public library", "civic_resources"),
        ("where is city hall", "civic_resources"),
    ],
)
def test_resolves_to_expected_intent(query, intent_key):
    resolved = resolve(query)
    assert resolved is not None, f"{query!r} should resolve"
    assert resolved.intent_key == intent_key


@pytest.mark.parametrize(
    "query, intent_key",
    [
        # The new water/parks rules must NOT steal these from earlier rules.
        ("rv park for the weekend", "lodging_find"),
        ("hotels near the lake", "lodging_find"),
        ("pizza by the lake", "eat_find"),
    ],
)
def test_new_buckets_do_not_regress_existing(query, intent_key):
    resolved = resolve(query)
    assert resolved is not None
    assert resolved.intent_key == intent_key


def test_service_slot_and_subcat_grounding():
    resolved = resolve("i need a plumber in english village")
    assert resolved is not None
    assert resolved.intent_key == "find_service"
    assert resolved.slots["service"] == "plumber"
    assert resolved.slots["area"] == "English Village"
    # The service routes to a real subcategory group, never a fake category.
    route = dicts.SERVICE_DICT[resolved.slots["service"]]
    assert route.subcat in dicts.SERVICE_SUBCAT_GROUPS


def test_open_now_slot():
    resolved = resolve("is there a dentist open now")
    assert resolved is not None
    assert resolved.intent_key == "find_service"
    assert resolved.slots.get("open_now") is True


def test_cuisine_and_area_slots():
    resolved = resolve("pizza near downtown")
    assert resolved is not None
    assert resolved.slots["cuisine"] == "pizza"
    assert resolved.slots["area"] == "Downtown"


def test_age_normalization_equivalence():
    """master spec §4.2: 'my 8-year-old' and 'a 9 year old' -> same kids band."""
    a = resolve("swim lessons for my 8-year-old")
    b = resolve("swim lessons for a 9 year old")
    assert a is not None and b is not None
    assert a.slots["age_band"] == b.slots["age_band"] == "kids"


@pytest.mark.parametrize(
    "phrase, band",
    [
        ("for my 2 year old", "toddler"),
        ("a 7-year-old", "kids"),
        ("my 15 year old", "teen"),
        ("classes for seniors", "senior"),
        ("toddler music class", "toddler"),
    ],
)
def test_parse_age_band(phrase, band):
    assert dicts.parse_age_band(phrase) == band


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "what is the meaning of life",
        "tell me a joke",
        "asdf qwer zxcv",
        # venue-specific event questions -> entity-aware path, not a generic list
        "next event at fake provider inc",
        "what's happening at the bridge tonight",
        "live music at mudshark brewery",
    ],
)
def test_falls_through_when_unconfident(query):
    assert resolve(query) is None


def test_service_dict_only_routes_to_real_groups():
    """Every SERVICE_DICT route targets a real subcategories.py Services group."""
    for term, route in dicts.SERVICE_DICT.items():
        assert route.subcat in dicts.SERVICE_SUBCAT_GROUPS, term
