"""2026-06-30 search audit 3B: the card category tag reads the authoritative
primary-leaf category, not Google's freeform google_primary_category / legacy
category (which produced "Rv Park", "Indoor Playground", "Kids Lessons")."""

from __future__ import annotations

from app.chat.component_builders import _trade_category_label


def test_prefers_primary_leaf_label():
    row = {
        "primary_category_label": "RV Parks & Campgrounds",
        "google_primary_category": "rv_park",
        "category": "lake_recreation",
    }
    assert _trade_category_label(row) == "RV Parks & Campgrounds"


def test_falls_back_to_google_then_legacy_when_no_leaf():
    assert _trade_category_label({"google_primary_category": "amusement_park"}) == "Amusement Park"
    assert _trade_category_label({"category": "food_drink"}) == "Food Drink"
    assert _trade_category_label({}) == ""


def test_blank_primary_label_ignored():
    # An empty/whitespace leaf label must not blank the tag — fall back.
    row = {"primary_category_label": "  ", "google_primary_category": "bowling_alley"}
    assert _trade_category_label(row) == "Bowling Alley"
