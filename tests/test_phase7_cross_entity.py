"""Phase 7 — cross-entity multi-domain chat queries."""

from __future__ import annotations

from app.chat.entity_intent import detect_multi_domain_category_slugs
from app.chat.intent_classifier import classify


def test_dog_breakfast_multi_domain() -> None:
    slugs = detect_multi_domain_category_slugs("where can I take my dog for breakfast?")
    assert slugs is not None
    assert "pets" in slugs
    assert "eat-drink" in slugs


def test_groceries_and_coffee() -> None:
    slugs = detect_multi_domain_category_slugs("groceries and coffee near me")
    assert slugs is not None
    assert "shopping-essentials" in slugs
    assert "eat-drink" in slugs


def test_single_domain_coffee_only() -> None:
    slugs = detect_multi_domain_category_slugs("where can I get coffee")
    assert slugs is None or len(slugs) < 2


def test_classify_attaches_multi_domain() -> None:
    ir = classify("dog-friendly breakfast spots")
    assert ir.multi_domain_category_slugs is not None
    assert len(ir.multi_domain_category_slugs) >= 2


def test_connector_with_one_noun_expands() -> None:
    slugs = detect_multi_domain_category_slugs("coffee and groceries")
    assert slugs is not None
    assert len(slugs) >= 2


def test_park_and_trail_with_food() -> None:
    slugs = detect_multi_domain_category_slugs("park and breakfast")
    assert slugs is not None
    assert "outdoors-parks-trails" in slugs
    assert "eat-drink" in slugs


def test_plain_plumber_single_domain() -> None:
    slugs = detect_multi_domain_category_slugs("I need a plumber")
    assert slugs is None


def test_dog_parks_phrase() -> None:
    slugs = detect_multi_domain_category_slugs("dog parks and pet stores")
    assert slugs is not None
    assert "pets" in slugs
