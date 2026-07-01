"""2026-06-30 search audit 3D: cannabis dispensaries split from smoke/vape.

`dispensary`/`cannabis`/`marijuana`/`weed` route to the new cannabis-dispensaries
leaf; `smoke shops`/`vape shops` stay on smoke-vape-and-cannabis. The new slug is
declared in the taxonomy seed so the drift guard passes.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.categories.leaf_query import _QUERY_TO_LEAF, _normalize

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"


def test_dispensary_terms_route_to_cannabis_leaf():
    for raw in ("dispensary", "dispensaries", "cannabis", "cannabis dispensary",
                "marijuana", "marijuana dispensary", "weed"):
        norm = _normalize(raw)
        assert _QUERY_TO_LEAF.get(norm) == "cannabis-dispensaries", (raw, norm)


def test_smoke_and_vape_terms_stay_on_smoke_leaf():
    for raw in ("smoke shops", "vape shops"):
        assert _QUERY_TO_LEAF.get(_normalize(raw)) == "smoke-vape-and-cannabis", raw


def test_cannabis_leaf_declared_in_seed():
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    leaves = (data.get("shopping-and-retail") or {}).get("leaves") or {}
    assert "cannabis-dispensaries" in leaves
