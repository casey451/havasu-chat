"""B6 — non-food Eat & Drink pollution detection (looks_non_food).

Mirrors the prod scenarios the heuristic was built for (2026-06-04: a wedding
planner / florist surfaced under "good restaurants").
"""

from __future__ import annotations

from app.categories.eat_pollution import flatten_label, looks_non_food


def test_real_restaurant_not_flagged() -> None:
    assert looks_non_food("food_drink", "restaurant", ["Mexican restaurant"]) is False
    assert looks_non_food("food", "coffee shop", ["Cafe"]) is False


def test_wedding_planner_flagged() -> None:
    # Google primary is the non-food label → deny-list catches it.
    assert looks_non_food("food_drink", "event planner", ["Wedding planner", "Florist"]) is True


def test_secondary_caterer_tag_does_not_rescue() -> None:
    # A florist with a secondary "Caterer" Google tag stays flagged — the food
    # allow-list only trusts the PRIMARY label.
    assert looks_non_food("food_drink", "florist", ["Florist", "Caterer"]) is True


def test_real_caterer_not_flagged() -> None:
    # A genuine caterer carries it as the primary label → protected.
    assert looks_non_food("food_drink", "caterer", ["Caterer"]) is False


def test_bare_service_category_flagged() -> None:
    # Anchored ^services?$ matches a bare category even with no Google labels.
    assert looks_non_food("Service", None, None) is True


def test_flatten_label_handles_list_and_none() -> None:
    assert flatten_label(["A", "B"]) == "A B"
    assert flatten_label(None) == ""
    assert flatten_label("x") == "x"
