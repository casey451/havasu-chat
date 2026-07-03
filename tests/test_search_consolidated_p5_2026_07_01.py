"""2026-07-01 consolidated Phase 5 — backfill-polish routing terms.

The rows ride scripts/backfill_search_gaps_2026_07_01.py (gated); this pins the
code half: weight-loss ([ASK #6] default = med-spas), animal shelter / humane
society, and the things-to-do polish (cliff jumping / Copper Canyon /
lighthouses — Copper Canyon and the replica-trail rows already exist).
"""

from __future__ import annotations

from app.categories.leaf_query import (
    _QUERY_TO_LEAF,
    _QUERY_TO_LEAF_BACKFILLS_2026_07_01,
    _normalize,
)

_CASES = {
    "weight loss": "med-spas-and-aesthetics",
    "weight loss clinic": "med-spas-and-aesthetics",
    "animal shelter": "nonprofits-and-charities",
    "humane society": "nonprofits-and-charities",
    "cliff jumping": "beaches-and-swim-areas",
    "copper canyon": "beaches-and-swim-areas",
    "lighthouse": "landmarks-and-sights",
    "lighthouses": "landmarks-and-sights",
}


def test_backfill_terms_route_to_expected_leaf():
    for raw, slug in _CASES.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


def test_backfill_keys_normalize_to_themselves():
    for terms in _QUERY_TO_LEAF_BACKFILLS_2026_07_01.values():
        for term in terms:
            assert _normalize(term) == term, (term, _normalize(term))


def test_backfill_terms_dont_override_prior_entries():
    # setdefault must preserve pre-existing mappings around these words.
    assert _QUERY_TO_LEAF["med spas"] == "med-spas-and-aesthetics"
    assert _QUERY_TO_LEAF["nonprofits"] == "nonprofits-and-charities"
    assert _QUERY_TO_LEAF["beaches"] == "beaches-and-swim-areas"
    assert _QUERY_TO_LEAF["landmarks"] == "landmarks-and-sights"


def test_backfill_terms_dont_corrupt_spell_vocab():
    from app.chat.normalizer import spell_correct

    for phrase in ("light house paint", "copper wire", "canyon trail",
                   "cliff notes", "weight bench"):
        assert spell_correct(phrase) == phrase, (phrase, spell_correct(phrase))
