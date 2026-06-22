"""P1: civic/government events route to their own "City & Government" bucket,
not the leisure-oriented "Happening today" group."""

from app.home.event_buckets import (
    GROUP_DEFS,
    GROUP_NOUNS,
    TIER_COMMUNITY,
    TIER_OTHER,
    group_for_tier,
    is_civic,
)


def test_civic_bucket_present_and_ordered():
    keys = [k for k, _label, _icon in GROUP_DEFS]
    assert "civic" in keys
    # City & Government sits after the Seniors overlay, before leisure buckets.
    assert keys.index("civic") == keys.index("seniors") + 1
    assert keys.index("civic") < keys.index("music")


def test_civic_has_rollup_nouns():
    assert "civic" in GROUP_NOUNS
    singular, plural = GROUP_NOUNS["civic"]
    assert singular and plural


def test_is_civic_matches_meetings_not_leisure():
    assert is_civic("City Council Meeting")
    assert is_civic("Board of Adjustment")
    assert is_civic("Planning and Zoning Commission")
    assert is_civic("Public Hearing on the Budget")
    # tag-only routing (the civic scrapers tag these rows)
    assert is_civic("Regular Session", ["civic", "government", "meeting"])
    # "dj" inside "adjustment" must not leak; leisure stays non-civic
    assert not is_civic("DJ Night at the Lighthouse")
    assert not is_civic("Sunset Paddle")
    assert not is_civic("Yoga in the Park")


def test_group_for_tier_routes_civic_even_when_recurring():
    # A regularly-scheduled council meeting must NOT be swept into the Fitness
    # class list — civic is checked before the recurring/class branch.
    assert group_for_tier(TIER_COMMUNITY, recurring=True,
                          title="City Council Meeting") == "civic"
    assert group_for_tier(TIER_COMMUNITY, recurring=False,
                          title="Board of Adjustment Meeting") == "civic"
    # Non-civic community item still lands in "Happening today".
    assert group_for_tier(TIER_OTHER, recurring=False,
                          title="Quilt Gala") == "events"
