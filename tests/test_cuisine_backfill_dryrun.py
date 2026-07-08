"""Pins the WS9a cuisine backfill dry-run's deterministic classifier.

The script itself is read-only ops (needs prod DB, runs in CI), but its pure
proposal function must be reproducible and conservative: specific cuisines get
proposed from name/type/snippet keywords; generic tokens (grill/pub/brewery)
are left ``None`` for the LLM tier rather than force-classified.
"""

from __future__ import annotations

from app.categories.subcategories import cuisine_slugs_in_order
from scripts.cuisine_backfill_dryrun import _propose_deterministic


def test_name_keyword_proposes_specific_cuisine() -> None:
    assert _propose_deterministic("Bad Miguel's Mexican", None, None, None) == "mexican"
    assert _propose_deterministic("Javelina Cantina", None, None, None) == "mexican"
    assert _propose_deterministic("Rosati's Pizza", None, None, None) == "pizza"
    assert _propose_deterministic("Rolling Smoke BBQ", None, None, None) == "bbq"
    assert _propose_deterministic("ZENSHI Handcrafted Sushi", None, None, None) == "japanese"


def test_google_type_and_snippet_signals_used() -> None:
    assert _propose_deterministic("Tokyo Grill", "restaurant", ["ramen_restaurant"], None) == "japanese"
    snippets = [{"text": "best carne asada tacos in town"}]
    assert _propose_deterministic("The Corner Spot", None, None, snippets) == "mexican"


def test_generic_tokens_left_for_llm_tier() -> None:
    # grill / pub / brewery / kitchen are too generic to force a cuisine.
    for name in ("Barley Brothers Brewery", "The Foundry", "Kitchen 738", "College Street Pub"):
        assert _propose_deterministic(name, None, None, None) is None


def test_only_ever_returns_a_slug_in_the_fixed_enum() -> None:
    valid = set(cuisine_slugs_in_order())
    got = _propose_deterministic("Filiberto's Mexican Food", None, None, None)
    assert got in valid
