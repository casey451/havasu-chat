"""A provider literally named after the town ("Havasu") must not hijack generic
locality queries like "where should I stay in havasu"."""

from __future__ import annotations

from app.chat.entity_matcher import (
    _is_pure_locality_needle,
    _needles_for_canonical,
    match_entity_with_rows,
)


def test_locality_only_names_have_no_needles() -> None:
    assert _needles_for_canonical("Havasu") == frozenset()
    assert _needles_for_canonical("Lake Havasu City") == frozenset()
    assert _is_pure_locality_needle("havasu") is True
    # Real business names are kept (narrower than the #47 stopword set).
    assert _is_pure_locality_needle("the inn") is False


def test_distinctive_names_keep_their_needles() -> None:
    needles = _needles_for_canonical("Havasu Lanes")
    assert needles, "a distinctively-named provider must keep matchable needles"
    assert any("lanes" in n for n in needles)


def test_locality_query_does_not_match_locality_only_provider() -> None:
    assert match_entity_with_rows("where should i stay in havasu", ["Havasu"]) is None
    # A distinctively-named provider still resolves by name.
    res = match_entity_with_rows("hours for havasu lanes", ["Havasu Lanes"])
    assert res is not None and res[0] == "Havasu Lanes"


# --- C-PR-4 (hunt 2026-06-11): typo scorers must not ride the locality token --


def test_typo_path_does_not_score_on_locality_token_alone() -> None:
    """partial_token_set_ratio gives a flat 100 for one shared token; with
    "havasu" shared by half the catalog, a coincidental per-token guard pass
    (partial_ratio("stitchers","heroes") == 80.0 exactly) let an unrelated
    needle tie the real match. The typo scorers now run on the non-locality
    form of the stripped query."""
    decoy = match_entity_with_rows(
        "tell me about havasu stitchers", ["HAVASU HEROES MEMORIAL CONCERT"]
    )
    assert decoy is None or decoy[1] < 100.0
    # With both rows present the real entity must win.
    both = match_entity_with_rows(
        "tell me about havasu stitchers",
        ["HAVASU HEROES MEMORIAL CONCERT", "Havasu Stitchers Community Outreach Sewing"],
    )
    assert both is not None and both[0] == "Havasu Stitchers Community Outreach Sewing"


def test_locality_only_typo_query_keeps_previous_behavior() -> None:
    # Stripped query that is ONLY locality words falls back to the old scoring
    # input rather than an empty string.
    res = match_entity_with_rows("hours for havasu lanes", ["Havasu Lanes"])
    assert res is not None and res[0] == "Havasu Lanes"
