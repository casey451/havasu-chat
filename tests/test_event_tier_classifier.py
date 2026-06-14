"""Event tier classifier — word-boundary hints + civic routing.

Regression suite for the 2026-06-10 live bug where "Board of Adjustment
Meeting" was the sole item under Music & nightlife on /events-ui (and the
top home week-strip headline): the old substring matcher saw the music hint
"dj" inside "aDJustment". Hints now match on word boundaries with a plural
or gerund tail, civic/government events route to the Community tier, and
"fest" keeps suffix matching so compound festival names still rank special.
"""

from __future__ import annotations

import pytest

from app.home.sandstone import (
    _TIER_AQUATIC,
    _TIER_CLASS,
    _TIER_COMMUNITY,
    _TIER_MUSIC,
    _TIER_OTHER,
    _TIER_SPECIAL,
    _TIER_WATER,
    _event_tier,
)


def tier(title: str, tags: list[str] | None = None, *, featured: bool = False,
         recurring: bool = False) -> int:
    return _event_tier(title=title, tags=tags, featured=featured, recurring=recurring)


# --- the live bug ----------------------------------------------------------

def test_board_of_adjustment_is_community_not_music():
    assert tier("Board of Adjustment Meeting") == _TIER_COMMUNITY


def test_civic_tags_route_to_community():
    # The civic scraper already tags these rows; tags join the haystack.
    assert tier("Board of Adjustment Meeting", ["civic", "government", "meeting"]) == _TIER_COMMUNITY


@pytest.mark.parametrize("title", [
    "City Council Special Session",
    "Planning Commission Public Hearing",
    "School Board Meeting",
])
def test_government_meetings_are_community(title):
    assert tier(title) == _TIER_COMMUNITY


# --- substring false-positives the boundary fix kills ----------------------

def test_dj_substring_no_longer_fires_inside_words():
    assert tier("Bird Adjusting Society") == _TIER_OTHER


def test_spin_substring_no_longer_fires_inside_inspiring():
    # "Inspiring …" must not read as a spin class; workshop → community.
    assert tier("Inspiring Watercolors Workshop") == _TIER_COMMUNITY


def test_fish_substring_no_longer_fires_inside_selfish():
    assert tier("Selfish Giants Book Club") == _TIER_COMMUNITY  # club, not water


# --- coverage the boundaries must NOT lose ---------------------------------

def test_real_dj_events_still_music():
    assert tier("DJ Night at the Turtle") == _TIER_MUSIC
    assert tier("DJs on the Beach") == _TIER_MUSIC


def test_fest_suffix_still_special():
    assert tier("Oktoberfest") == _TIER_SPECIAL
    assert tier("Winterfest Street Party") == _TIER_SPECIAL


def test_gerund_and_plural_tails_still_match():
    assert tier("Sunrise Kayaking") == _TIER_WATER
    assert tier("Concerts in the Park") == _TIER_MUSIC
    # Swim lessons happen in the POOL — Aquatic Center, not the lake.
    assert tier("Swimming Lessons") == _TIER_AQUATIC
    assert tier("Spinning") == _TIER_CLASS


# --- pool (Aquatic Center) is NOT "on the water" (the lake) -----------------

def test_pool_activities_tier_aquatic_not_water():
    # The live bug: Aquatic Center pool sessions wore the lake pill. Pool words
    # now route to their own Aquatic Center tier, never On-the-water.
    assert tier("Open Swim") == _TIER_AQUATIC
    assert tier("Free Family Swim") == _TIER_AQUATIC
    assert tier("Lap Swim (Morning)") == _TIER_AQUATIC
    assert tier("Aqua Zumba") == _TIER_AQUATIC
    assert tier("Water Aerobics") == _TIER_AQUATIC


def test_genuine_lake_activities_stay_on_the_water():
    # Literally on Lake Havasu / the Bridgewater Channel — these keep the
    # On-the-water tier (no pool word present).
    assert tier("Sunset Kayak Tour") == _TIER_WATER
    assert tier("Sunset Paddle") == _TIER_WATER
    assert tier("Boat Parade") == _TIER_SPECIAL  # "parade" is a special
    assert tier("Channel Cleanup") == _TIER_WATER


# --- unchanged baseline behavior -------------------------------------------

def test_class_signal_beats_music_and_water():
    assert tier("Beginner Pilates (Wed/Fri)") == _TIER_CLASS


def test_untyped_one_off_is_other_and_recurring_is_class():
    assert tier("Polymer Clay Adults") == _TIER_OTHER
    assert tier("Polymer Clay Adults", recurring=True) == _TIER_CLASS


def test_featured_always_special():
    assert tier("Anything At All", featured=True) == _TIER_SPECIAL


def test_water_and_community_baselines():
    assert tier("Sunrise Kayak Social") == _TIER_WATER
    assert tier("Farmers Market") == _TIER_COMMUNITY
    assert tier("Rowdy Bingo at Grapes N Grains") == _TIER_COMMUNITY


def test_musical_theatre_no_longer_reads_as_music():
    # Deliberate behavior shift: the substring matcher tiered "…Musical…"
    # as music/nightlife; with word boundaries a stage musical is an
    # untyped one-off (Events group), which reads better than "nightlife".
    assert tier("Grace Arts Live Presents The SpongeBob Musical Youth Edition") == _TIER_OTHER
