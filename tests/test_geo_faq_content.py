"""LANE B6 — verified GEO/AEO FAQ content asset.

Asserts: (1) every CATEGORY_FILTERS slug maps to a content target;
(2) the 10 top intents are present; (3) has_data=False targets render the
honest "coverage being built" copy (no business names / counts) and point
users to /contribute; (4) FAQ/landing text carries no fabrication markers.
"""

from __future__ import annotations

from app.categories.queries import CATEGORY_FILTERS
from app.geo import faq_content

# The 10 top intents the lane covers (verified content set).
_TOP_INTENTS = {
    "eat_find",
    "events_weekend",
    "find_service",
    "urgent_care",
    "gym_fitness",
    "kids_lessons",
    "lodging_find",
    "boat_rental",
    "parks_trails",
    "cheapest_gas",
}


def test_every_category_filter_slug_has_verified_content() -> None:
    slugs = set(faq_content.all_category_slugs())
    missing = set(CATEGORY_FILTERS) - slugs
    assert not missing, f"category slugs without verified GEO content: {sorted(missing)}"


def test_all_top_intents_present() -> None:
    keys = set(faq_content.all_intent_keys())
    assert _TOP_INTENTS <= keys, f"missing intents: {sorted(_TOP_INTENTS - keys)}"


def test_category_target_shape() -> None:
    t = faq_content.category_faq_target("eat-drink")
    assert t is not None
    assert t.has_data is True
    assert t.title.startswith("Restaurants")
    assert t.meta_description
    assert len(t.faqs) >= 1
    # FAQ list is template/JSON-LD friendly dicts.
    assert all(set(f) == {"q", "a"} for f in t.faq_list)


def test_unknown_slug_returns_none() -> None:
    assert faq_content.category_faq_target("not-a-real-slug") is None
    assert faq_content.category_faq_target(None) is None
    assert faq_content.intent_faq_target("nope") is None


def test_empty_coverage_targets_are_honest() -> None:
    """has_data=False targets must not name businesses/counts and must point to
    /contribute (the coverage-being-built copy), never fabricate listings."""
    fabricated_digits = ("928)", "(760)", "(719)", "(951)", "(847)", "(800)")
    for slug in faq_content.all_category_slugs():
        t = faq_content.category_faq_target(slug)
        assert t is not None
        if t.has_data:
            continue
        joined = (t.intro + " " + " ".join(f["a"] for f in t.faq_list)).lower()
        assert "/contribute" in joined, f"{slug}: empty target must invite contributions"
        # No phone numbers (a strong proxy for a fabricated concrete listing).
        for marker in fabricated_digits:
            assert marker not in joined, f"{slug}: empty-coverage copy leaked a phone number"


def test_no_fabrication_markers_anywhere() -> None:
    """Guard against placeholder/AI-ish fabrication tells slipping into copy."""
    bad_markers = ("lorem ipsum", "as an ai", "[insert", "todo:", "xxxx", "example.com")
    targets = [faq_content.category_faq_target(s) for s in faq_content.all_category_slugs()]
    targets += [faq_content.intent_faq_target(k) for k in faq_content.all_intent_keys()]
    for t in targets:
        assert t is not None
        blob = (t.title + t.intro + t.meta_description + " ".join(
            f["q"] + f["a"] for f in t.faq_list
        )).lower()
        for marker in bad_markers:
            assert marker not in blob, f"{t.key}: fabrication marker {marker!r}"


def test_grounded_fact_traces_to_verified_content() -> None:
    """A concrete fact rendered for eat-drink must exist verbatim in the asset
    (the FAQ/JSON-LD never invents facts beyond the verified content)."""
    t = faq_content.category_faq_target("eat-drink")
    assert t is not None
    all_answers = " ".join(f["a"] for f in t.faq_list)
    # These specific facts are part of the verified content set.
    assert "Dos Amigos Taco's" in all_answers
    assert "2231 McCulloch Blvd N #107" in all_answers
    assert "(928) 302-3282" in all_answers
