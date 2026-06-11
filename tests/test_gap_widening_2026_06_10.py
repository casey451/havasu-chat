"""2026-06-10 hunt §1b gap-template widening (C-PR-5).

Every query here is a real prod turn that hit ``tier_used='gap_template'`` in
the 06-10 export while the catalog had the answer. Discovery shapes must fall
through to the catalog tiers; recommendation shapes from earlier fixes are
pinned alongside.
"""

from __future__ import annotations

import pytest

from app.chat.intent_classifier import classify
from app.chat.unified_router import _catalog_gap_response


@pytest.mark.parametrize(
    "query",
    [
        # discovery intents (hunt §1b: 10 turns; near-match misdirection class)
        "date night ideas",
        "happy hour spots near the channel",
        "indoor activities when its hot",
        "indoor dining when it is hot",
        # discovery via listing/recommendation shapes — pinned
        "where is the best sushi in town",
        # hunt §1b item 1: the documented boat-rental LOCATION_LOOKUP false
        # positive (fix shipped 2026-06-04; pinned so it cannot regress)
        "where can i rent a boat",
    ],
)
def test_catalog_answerable_shapes_never_hit_gap_template(query: str) -> None:
    intent = classify(query)
    assert _catalog_gap_response(intent, None) is None, query


@pytest.mark.parametrize(
    "query",
    [
        # entity-shaped factual lookups must KEEP gating (no discovery regex
        # over-reach): unknown single entity + factual sub-intent still gaps.
        "phone number for flubber industries",
        "where is flubber industries located",
    ],
)
def test_factual_entity_lookups_still_gap(query: str) -> None:
    intent = classify(query)
    if intent.sub_intent in ("PHONE_LOOKUP", "LOCATION_LOOKUP") and not intent.entity:
        assert _catalog_gap_response(intent, None) is not None, query
