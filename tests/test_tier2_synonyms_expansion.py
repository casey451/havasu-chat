"""2026-06-11 Tier-2 synonym widening — needle-set expansion + invariants."""

from __future__ import annotations

from app.chat.tier2_synonyms import (
    _CATEGORY_SYNONYM_GROUPS,
    _category_needle_set,
    _category_synonyms,
)


def test_new_trade_groups_expand():
    cases = {
        "vehicle wraps": "car wrap",
        "window tint": "tinting",
        "detailing": "boat detailing",
        "towing": "roadside assistance",
        "locksmith": "lockout service",
        "golf cart": "golf cart repair",
        "auto glass": "windshield replacement",
        "laundromat": "dry cleaning",
        "property management": "rental management",
        "junk removal": "hauling",
        "pressure washing": "power washing",
        "appliance repair": "washer repair",
        "garage door": "overhead door",
        "tree service": "stump grinding",
        "pet sitting": "dog walker",
        "funeral home": "cremation",
        "hearing aids": "audiologist",
        "septic": "septic pumping",
        "boat storage": "self storage",
        "sign shop": "printing",
    }
    for term, expected_sibling in cases.items():
        syns = _category_synonyms(term)
        assert expected_sibling in syns, (term, syns)


def test_needle_set_includes_singulars():
    needles = _category_needle_set("vehicle wraps")
    assert "vehicle wrap" in needles
    assert "car wrap" in needles


def test_original_groups_untouched():
    assert "cafe" in _category_synonyms("coffee shop")
    assert "drugstore" in _category_synonyms("pharmacy")
    assert "car repair" in _category_synonyms("mechanic")


def test_unknown_term_returns_self():
    assert _category_synonyms("unicycle polish") == ("unicycle polish",)


def test_groups_are_lowercase_and_nonempty():
    for group in _CATEGORY_SYNONYM_GROUPS:
        assert group, "empty synonym group"
        for term in group:
            assert term == term.strip().lower(), term
