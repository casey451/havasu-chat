"""2026-06-30 follow-on routing: parasailing + the new scuba-and-dive leaf.

The data backfill added Havasu Parasail (jet-ski leaf) and created the
scuba-and-dive leaf (re-homing Scuba Training). These assert the phrasings reach
them, that keys normalize to themselves, and that the new leaf slug is declared
in the taxonomy seed so the drift guard (test_leaf_query_additions) passes.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.categories.leaf_query import (
    _QUERY_TO_LEAF,
    _QUERY_TO_LEAF_SEARCH_ADD2_2026_06_30,
    _normalize,
)

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"

_CASES = {
    "parasailing": "jet-ski-and-watersports",
    "parasail": "jet-ski-and-watersports",
    "scuba": "scuba-and-dive",
    "scuba diving": "scuba-and-dive",
    "scuba lessons": "scuba-and-dive",
    "dive shop": "scuba-and-dive",
}


def test_followon_terms_route_to_expected_leaf():
    for raw, slug in _CASES.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


def test_followon_keys_normalize_to_themselves():
    for terms in _QUERY_TO_LEAF_SEARCH_ADD2_2026_06_30.values():
        for term in terms:
            assert _normalize(term) == term, (term, _normalize(term))


def test_scuba_leaf_declared_in_seed():
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    leaves = (data.get("on-the-water") or {}).get("leaves") or {}
    assert "scuba-and-dive" in leaves, "scuba-and-dive must be in the taxonomy seed"
