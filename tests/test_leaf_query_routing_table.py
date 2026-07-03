"""Locks the collapsed leaf-query routing table (audit 2026-07-01 refactor).

``app.categories.leaf_query`` builds one canonical ``term -> slug`` table
(``_QUERY_TO_LEAF``) from a hand-authored core plus several generation-stamped
contribution blocks, folded in via a single first-writer-wins merge. These
tests are the safety net that let the eight near-identical per-block merge loops
collapse to one:

* no two contributing blocks (base included) route the SAME term to DIFFERENT
  slugs — so the merge order is provably irrelevant and nothing is silently
  dropped; and
* the merged table is byte-identical to the committed snapshot (regenerate the
  snapshot deliberately when routing genuinely changes).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.categories import leaf_query as lq

_SNAPSHOT = Path(__file__).parent / "snapshots" / "leaf_query_routing_snapshot.json"


def test_merged_routing_table_matches_snapshot() -> None:
    """The built ``_QUERY_TO_LEAF`` equals the committed pre-collapse snapshot."""
    expected = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    assert lq._QUERY_TO_LEAF == expected


def test_no_cross_block_term_conflicts() -> None:
    """No term is routed to two different slugs across the contribution blocks.

    Collects every ``(term -> slug)`` any block asserts and checks each term
    resolves to a single slug that also equals the final merged value — proving
    the ``setdefault`` first-wins ordering never masks a real disagreement (base
    vs an addition, or one addition vs another).
    """
    term_to_slugs: dict[str, set[str]] = {}

    def _record(term: str, slug: str) -> None:
        term_to_slugs.setdefault(term, set()).add(slug)

    for block in lq._LEAF_TERM_BLOCKS:
        for slug, terms in block.items():
            for term in terms:
                _record(term, slug)
    for term, slug in lq._QUERY_TO_LEAF_BARE_FORMS_2026_06_20.items():
        _record(term, slug)

    conflicts = {
        term: slugs for term, slugs in term_to_slugs.items() if len(slugs) > 1
    }
    assert not conflicts, f"terms routed to multiple slugs across blocks: {conflicts}"

    # And every asserted routing survived into the final table unchanged (i.e.
    # the base core never overrode an addition with a *different* slug).
    mismatched = {
        term: (next(iter(slugs)), lq._QUERY_TO_LEAF.get(term))
        for term, slugs in term_to_slugs.items()
        if lq._QUERY_TO_LEAF.get(term) != next(iter(slugs))
    }
    assert not mismatched, f"addition term slug != final merged slug: {mismatched}"
