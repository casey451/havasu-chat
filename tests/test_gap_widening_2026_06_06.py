"""2026-06-06 gap-report widening — resolver/dicts coverage, spurious-entity
bypass, locality-aware matcher guard, bare-entity about path, and cache-key
canonicalization. Every case here is a real query mined from prod chat_logs
(30-day window) that paid Tier 2-full or Tier 3 before this change.
"""

from __future__ import annotations

import pytest

from app.chat.entity_matcher import match_entity_with_rows
from app.chat.intents.resolver import category_vocabulary, resolve
from app.chat.intents.runtime import _entity_match_spurious
from app.chat.llm_cache import make_cache_key
from app.chat.normalizer import canonicalize_for_cache
from app.chat.tier1_handler import _is_bare_entity_query
from app.chat.tier2_cache import _parser_cache_key

# ---------------------------------------------------------------------------
# Resolver / dict widening
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, intent_key, slot_key, slot_value",
    [
        ("where can i get good tacos", "eat_find", "cuisine", "mexican"),
        ("best happy hour in town", "eat_find", "cuisine", "happy hour"),
        ("best quick bites", "eat_find", "cuisine", "quick bites"),
        ("mountain biking", "parks_trails", None, None),
        ("mountian biking", "parks_trails", None, None),  # prod typo, "biking" carries it
        ("bike trails near me", "parks_trails", None, None),
        (
            "what activities can my 8 year old do after school hours",
            "kids_lessons",
            "age_band",
            "kids",
        ),
    ],
)
def test_gap_report_queries_resolve(query, intent_key, slot_key, slot_value):
    resolved = resolve(query)
    assert resolved is not None, query
    assert resolved.intent_key == intent_key
    if slot_key is not None:
        assert resolved.slots.get(slot_key) == slot_value


@pytest.mark.parametrize(
    "query, intent_key",
    [
        ("bike shop", "shopping_find"),  # retail stays retail
        ("buy a bike", "shopping_find"),
        ("boat repair shop", "boat_repair"),  # water bucket unaffected
    ],
)
def test_widening_does_not_leak_into_other_buckets(query, intent_key):
    resolved = resolve(query)
    assert resolved is not None
    assert resolved.intent_key == intent_key


def test_adult_activities_without_age_signal_still_falls_through():
    # "activities" alone must not claim kids_lessons (no band, no kid words).
    resolved = resolve("fun activities")
    assert resolved is None or resolved.intent_key != "kids_lessons"


def test_category_vocabulary_contains_dict_and_resolver_terms():
    vocab = category_vocabulary()
    for word in ("plumber", "plumb", "taco", "brewery", "yoga", "biking", "concert"):
        assert word in vocab, word


# ---------------------------------------------------------------------------
# Spurious-entity bypass (runtime guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "what is the best plumber in lake havasu",  # 8x in the 30-day window
        "electrician",
        "i need a plumber",
        "concerts in lake havasu",
        "what activities can my 8 year old do after school hours",
    ],
)
def test_generic_category_queries_are_spurious_entity_matches(query):
    assert _entity_match_spurious(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "mudshark brewery",  # distinctive name token
        "tell me about havasu stitchers",  # distinctive non-locality token
        "altitude trampoline park hours today",
        "what water exercise classes does the aquatic center offer",
        "morgan electric phone number",
    ],
)
def test_distinctive_queries_keep_the_entity_guard(query):
    assert _entity_match_spurious(query) is False


# ---------------------------------------------------------------------------
# Entity matcher — locality token must not satisfy the substring guard
# ---------------------------------------------------------------------------


def test_havasu_stitchers_no_longer_matches_havasu_suites():
    # Prod 2026-06: served "Havasu Suites — Travel Agency" for a quilting guild.
    hit = match_entity_with_rows("tell me about havasu stitchers", ["Havasu Suites"])
    assert hit is None


def test_genuine_havasu_named_provider_still_matches():
    hit = match_entity_with_rows("tell me about havasu suites", ["Havasu Suites"])
    assert hit is not None
    assert hit[0] == "Havasu Suites"


def test_trade_superlative_match_unaffected():
    # Backlog #52 contract must keep holding after the guard change.
    hit = match_entity_with_rows(
        "what is the best plumber in lake havasu", ["All Seasons Plumbing"]
    )
    assert hit is not None
    assert hit[0] == "All Seasons Plumbing"


def test_locality_only_query_keeps_previous_behavior():
    # All content tokens are locality words -> old unconstrained guard applies.
    hit = match_entity_with_rows("lake havasu marina", ["Lake Havasu Marina"])
    assert hit is not None


# ---------------------------------------------------------------------------
# Bare-entity about path (tier1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, entity, expected",
    [
        ("mudshark brewery", "Mudshark Brewery and Public House", True),
        ("the tap room", "The Tap Room", True),
        ("mudshark brewery menu", "Mudshark Brewery and Public House", False),
        ("is mudshark any good", "Mudshark Brewery and Public House", False),
        ("electrician", "Morgan Electric", False),  # not a name subset
        ("", "Mudshark Brewery and Public House", False),
        ("mudshark brewery", None, False),
    ],
)
def test_is_bare_entity_query(query, entity, expected):
    assert _is_bare_entity_query(query, entity) is expected


# ---------------------------------------------------------------------------
# Cache-key canonicalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant, canonical",
    [
        ("what restaurants are open now in lake havasu", "what restaurants are open now"),
        ("what restaurants are open now in lake havasu city", "what restaurants are open now"),
        ("what restaurants are open now in town", "what restaurants are open now"),
        ("what restaurants are open now near me", "what restaurants are open now"),
        ("hey hava, what restaurants are open now", "what restaurants are open now"),
        ("please what restaurants are open now", "what restaurants are open now"),
        ("what restaurants are open now please", "what restaurants are open now"),
        ("what restaurants are open now in town please", "what restaurants are open now"),
    ],
)
def test_canonicalize_folds_no_intent_phrasing(variant, canonical):
    assert canonicalize_for_cache(variant) == canonical


def test_canonicalize_preserves_distinct_intents():
    a = canonicalize_for_cache("what restaurants are open now")
    b = canonicalize_for_cache("what restaurants are open tomorrow")
    assert a != b
    # Locality INSIDE an entity name is not a suffix and must survive.
    assert canonicalize_for_cache("phone for the lake havasu marina") == (
        "phone for the lake havasu marina"
    )


def test_canonicalize_never_returns_empty():
    assert canonicalize_for_cache("near me") == "near me"
    assert canonicalize_for_cache("") == ""


def test_llm_cache_key_folds_variants():
    base = make_cache_key("what restaurants are open now", None)
    assert make_cache_key("what restaurants are open now in lake havasu", None) == base
    assert make_cache_key("hey hava, what restaurants are open now", None) == base
    assert make_cache_key("what restaurants are open tomorrow", None) != base


def test_tier2_parser_key_folds_variants():
    base = _parser_cache_key("any art classes this week", "2026-06-06")
    assert _parser_cache_key("any art classes this week in lake havasu", "2026-06-06") == base
    assert _parser_cache_key("any art classes this week near me", "2026-06-06") == base
    assert _parser_cache_key("any art classes this week", "2026-06-07") != base
    assert _parser_cache_key("any art classes next week", "2026-06-06") != base
