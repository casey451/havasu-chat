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
