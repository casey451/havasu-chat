"""Bucket overlay + categorization redesign (2026-06-19) — pure-function coverage.

* "Around town" + "Things to do" merge into "Happening today" (stable key
  ``events``); drop-in rec (Open Swim, Open Play) routes there via
  :func:`is_dropin_rec`.
* Kids & Family is an additive overlay, so :func:`group_for_tier` never returns
  ``"family"`` (nor ``"seniors"``) — both overlays are layered on in day_groups.
* "Open Mat" / Bridge City file under Martial Arts; pool classes get an
  "Aquatic fitness" subsection.
"""

from __future__ import annotations

from app.home.event_buckets import (
    GROUP_DEFS,
    TIER_CLASS,
    TIER_OTHER,
    group_for_tier,
    is_dropin_rec,
)
from app.home.events_views import _class_subgroup


def test_dropin_rec_routes_to_happening_today() -> None:
    for title in ("Open Swim", "Free Family Swim", "Pickleball Open Play", "Open Gym", "Public Skate"):
        assert is_dropin_rec(title), title
        assert group_for_tier(TIER_CLASS, recurring=True, title=title) == "events"


def test_open_mat_is_not_dropin_rec() -> None:
    assert not is_dropin_rec("Open Mat")
    assert not is_dropin_rec("Adult Open Mat & Rolls")


def test_group_for_tier_never_returns_overlay_keys() -> None:
    for title in ("Youth Karate", "Story Time", "Open Swim", "Senior Lunch", "Family Glow Bowling"):
        assert group_for_tier(TIER_CLASS, recurring=True, title=title) not in {"family", "seniors"}
        assert group_for_tier(TIER_OTHER, recurring=False, title=title) not in {"family", "seniors"}


def test_happening_today_label_and_keys() -> None:
    # "Happening today" → "Things to Do" and the new "learn" (Classes &
    # Workshops) top-level were added 2026-06-25. ``funzone`` stays a render-time
    # SECTION under Things to Do (Casey's call), not a top-level bucket here.
    labels = {key: label for key, label, _icon in GROUP_DEFS}
    assert labels["events"] == "Things to Do"
    assert {k for k, _l, _i in GROUP_DEFS} == {
        "events", "family", "seniors", "civic", "music", "water", "classes", "learn"
    }


def test_open_mat_and_bridge_city_route_to_martial_arts() -> None:
    assert _class_subgroup("Open Mat") == "Martial Arts"
    assert _class_subgroup("Grappling") == "Martial Arts"
    assert _class_subgroup("Adult Jiu Jitsu") == "Martial Arts"
    assert _class_subgroup("Fundamentals", "Bridge City BJJ") == "Martial Arts"
    assert _class_subgroup("Adult Program", "Bridge City Brazilian Jiu-Jitsu") == "Martial Arts"


def test_every_catalog_martial_arts_studio_routes_to_martial_arts() -> None:
    # Any class held at a martial-arts studio files under Martial Arts, by the
    # venue name — covering the live catalog's studios automatically (10 of 11
    # carry a discipline token; "Arevalo Academy" is the token-less straggler in
    # the explicit venue list).
    venues = [
        "Women KravMaga Self Defense for Women",
        "THE TAP ROOM JIU JITSU",
        "Lake Havasu Black Belt Academy LLC",
        "Four Dragons Martial Arts",
        "Havasu Shao-Lin Kempo",
        "Elite Martial Arts, Inc.",
        "Next Generation Mixed Martial Arts",
        "Seibukan Karate-Do",
        "Trinity Mixed Martial Arts",
        "Bridge City BJJ",
        "Arevalo Academy",
    ]
    for v in venues:
        # A generic, non-martial title still files under Martial Arts via the venue.
        assert _class_subgroup("Adult Class", v) == "Martial Arts", v


def test_pool_classes_get_aquatic_fitness_subsection() -> None:
    for title in ("Lap Swim", "Water Aerobics", "Aqua Zumba", "Deep Water Fitness"):
        assert _class_subgroup(title) == "Aquatic fitness", title
    assert _class_subgroup("Zumba") == "Strength & Cardio"
