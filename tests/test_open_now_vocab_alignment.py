"""Drift guard: the open-now category vocab must stay aligned across the matchers.

The open-now category list is intentionally expressed in three places —
`entity_intent._CATEGORY_OPEN_NOW_RE` (the Tier-1-suppression detector),
`tier2_business_shortcut._BARE_OPEN_NOW_RE` (the deterministic listing shape),
and `tier2_business_shortcut._OPEN_NOW_CAPTURE_TO_CATEGORY` (capture→canonical).
If someone adds a category to one but not the others, a "<cat> open now" query
silently half-works. This test fails on that drift so it's caught in CI rather
than on prod.
"""

from __future__ import annotations

import pytest

from app.chat.entity_intent import is_category_open_now_listing
from app.chat.tier2_business_shortcut import (
    _OPEN_NOW_CAPTURE_TO_CATEGORY,
    try_business_listing_shortcut,
)


@pytest.mark.parametrize("term", sorted(_OPEN_NOW_CAPTURE_TO_CATEGORY))
def test_capture_term_is_detected_and_listed(term: str) -> None:
    q = f"{term} open now"
    # 1) the Tier-1-suppression detector recognizes it as a category open-now query
    assert is_category_open_now_listing(q), f"{term!r} not in _CATEGORY_OPEN_NOW_RE"
    # 2) the deterministic shortcut produces an open-now listing for it
    f = try_business_listing_shortcut(q)
    assert f is not None and f.open_now is True, f"{term!r} not in bare open-now shortcut"
    # 3) it maps to its canonical category
    assert f.category == _OPEN_NOW_CAPTURE_TO_CATEGORY[term]
