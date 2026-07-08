"""Pins the WS9a cuisine backfill dry-run's classifier (hardened 2026-07-08).

The script itself is read-only ops (needs prod DB, runs in CI), but its pure
functions must be reproducible and conservative:
  * classify ONLY on name + Google types — never on review snippets (a single
    review word mis-tagged 24 of 34 rows in the first dry-run);
  * leave generic tokens (grill/pub/brewery) unclassified for the LLM tier;
  * flag Google-typed cuisines with no enum home as enum-ADDITION proposals,
    never force-fit them.
"""

from __future__ import annotations

from app.categories.subcategories import cuisine_slugs_in_order
from scripts.cuisine_backfill_dryrun import (
    _enum_gap,
    _propose_deterministic,
    _snippet_excerpt,
)


def test_name_keyword_proposes_specific_cuisine() -> None:
    assert _propose_deterministic("Bad Miguel's Mexican", None, None) == "mexican"
    assert _propose_deterministic("Javelina Cantina", None, None) == "mexican"
    assert _propose_deterministic("Rosati's Pizza", None, None) == "pizza"
    assert _propose_deterministic("Rolling Smoke BBQ", None, None) == "bbq"
    assert _propose_deterministic("ZENSHI Handcrafted Sushi", None, None) == "japanese"


def test_google_type_signal_used() -> None:
    assert _propose_deterministic("Tokyo Grill", "restaurant", ["ramen_restaurant"]) == "japanese"


def test_snippets_do_not_classify() -> None:
    # The single biggest first-dry-run defect: a keyword appearing ONLY in a
    # review snippet must NOT drive classification. Snippets are LLM context.
    snippets = [{"text": "best carne asada tacos in town"}]
    assert _propose_deterministic("Babaloo Lounge", "cuban_restaurant", None, snippets) is None
    assert _propose_deterministic("Montana's", "steak_restaurant", None, snippets) == "steakhouse"


def test_generic_tokens_left_for_llm_tier() -> None:
    for name in ("Barley Brothers Brewery", "The Foundry", "Kitchen 738", "College Street Pub"):
        assert _propose_deterministic(name, "restaurant", None) is None


def test_enum_gap_flags_unhomed_cuisines() -> None:
    assert _enum_gap("korean_restaurant", None) == "korean"
    assert _enum_gap("cuban_restaurant", None) == "cuban"
    assert _enum_gap("chicken_restaurant", None) == "fried_chicken"
    # A homed cuisine or a generic type is not an enum gap.
    assert _enum_gap("mexican_restaurant", None) is None
    assert _enum_gap("restaurant", None) is None
    # A gap-typed row must NOT get a forced deterministic proposal.
    assert _propose_deterministic("Flame Broiler", "korean_restaurant", None) is None


def test_snippet_excerpt_is_evidence_only() -> None:
    assert _snippet_excerpt([{"text": "great patio"}]) == "great patio"
    assert _snippet_excerpt(None) == ""
    assert len(_snippet_excerpt([{"text": "x" * 500}])) <= 160


def test_only_ever_returns_a_slug_in_the_fixed_enum() -> None:
    valid = set(cuisine_slugs_in_order())
    got = _propose_deterministic("Filiberto's Mexican Food", None, None)
    assert got in valid
