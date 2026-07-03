"""CI guardrail: no source category may drift out of the crosswalk.

The parity contract only holds if every category a source actually emits has a
crosswalk entry. This test enumerates the categories we KNOW the sources emit
(the golakehavasu loader's own CVB tables — built from crawling the live partner
directory) and asserts each resolves. A newly-observed CVB tag added to the
loader without a crosswalk entry fails CI, forcing a human to map it rather than
letting it silently fall to a default. See the parity plan Part A4.
"""

from __future__ import annotations

from app.contrib.golakehavasu_partners import (
    CVB_PRIMARY_CATEGORY_TO_SLUG,
    map_cvb_leaf,
)
from app.contrib.source_category_map import (
    CANONICAL_EVENT_CATEGORIES,
    KNOWN_BUSINESS_SOURCE_CATEGORIES,
    map_business_leaf,
    map_event_category,
    normalize_source_category,
)

# CVB tags that are NOT business categories (handled by the event pipeline) or
# are intentionally not a directory leaf. Keep this list explicit and small so a
# genuinely new/unmapped tag can't hide behind it.
_NON_BUSINESS_CVB_TAGS = {"events"}


def test_every_known_cvb_business_category_maps_to_a_leaf() -> None:
    """Every business CVB tag the loader recognises resolves to a leaf."""
    unmapped: list[str] = []
    for raw in CVB_PRIMARY_CATEGORY_TO_SLUG:
        key = normalize_source_category(raw)
        if key in _NON_BUSINESS_CVB_TAGS:
            continue
        # feed a neutral name so ambiguous tags fall to their default leaf
        if map_cvb_leaf(raw, "Neutral Business Name") is None:
            unmapped.append(raw)
    assert not unmapped, (
        "CVB business categories with NO crosswalk entry (add them to "
        f"app/contrib/source_category_map.py): {sorted(unmapped)}"
    )


def test_known_business_categories_all_resolve() -> None:
    """The crosswalk's own KNOWN set is internally consistent (each resolves)."""
    for cat in KNOWN_BUSINESS_SOURCE_CATEGORIES:
        assert map_business_leaf(cat, name="Neutral Business Name") is not None, cat


def test_event_tag_samples_map_or_are_explicit_misc() -> None:
    """A representative set of River Scene event tags all resolve (none silently
    unmapped). ``misc`` is an allowed, explicit landing."""
    sample = [
        "boating", "racing", "air-show", "music", "festival", "theater",
        "comedy-show", "movies", "farmers-market", "fundraiser", "christmas",
        "veterans-military", "pets", "pageant", "uncategorized",
    ]
    for tag in sample:
        canonical = map_event_category(tag)
        assert canonical is not None, tag
        assert canonical in CANONICAL_EVENT_CATEGORIES, canonical
