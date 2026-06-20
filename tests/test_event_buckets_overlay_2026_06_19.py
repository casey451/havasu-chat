"""Bucket overlay + categorization redesign (2026-06-19).

Pure-function coverage for the owner-approved changes:

* "Around town" + "Things to do today" merge into one **"Happening today"**
  group (stable key ``events``); all-day drop-in rec (Open Swim, Open Play)
  routes there via :func:`is_dropin_rec`.
* Kids & Family is an *additive overlay*, so :func:`group_for_tier` never returns
  ``"family"`` (the overlay is layered on in ``day_groups``).
* "Open Mat" / Bridge City file under Martial Arts; pool classes get their own
  "Aquatic fitness" subsection.

The day-level overlay behavior (kid items appearing in BOTH their primary group
and Kids & Family) is covered end-to-end in
``tests/test_events_ui_views.py::test_family_and_pool_classes_split_out``.
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
        # Even a recurring pool/court block routes to "Happening today", not classes.
        assert group_for_tier(TIER_CLASS, recurring=True, title=title) == "events"


def test_open_mat_is_not_dropin_rec() -> None:
    # "Open Mat" is jiu-jitsu, not drop-in pool/court rec — it must NOT route to
    # Happening today (it belongs in Martial Arts).
    assert not is_dropin_rec("Open Mat")
    assert not is_dropin_rec("Adult Open Mat & Rolls")


def test_group_for_tier_never_returns_family() -> None:
    # Kids & Family is an additive overlay built in day_groups, never a primary.
    for title in ("Youth Karate", "Story Time", "Open Swim", "Family Glow Bowling"):
        assert group_for_tier(TIER_CLASS, recurring=True, title=title) != "family"
        assert group_for_tier(TIER_OTHER, recurring=False, title=title) != "family"


def test_happening_today_is_the_merged_group_label() -> None:
    labels = {key: label for key, label, _icon in GROUP_DEFS}
    assert labels["events"] == "Happening today"
    # the bucket keys are unchanged (CSS swatches + many tests depend on them)
    assert {k for k, _l, _i in GROUP_DEFS} == {"events", "family", "music", "water", "classes"}


def test_open_mat_and_bridge_city_route_to_martial_arts() -> None:
    assert _class_subgroup("Open Mat") == "Martial Arts"
    assert _class_subgroup("Grappling") == "Martial Arts"
    assert _class_subgroup("Adult Jiu Jitsu") == "Martial Arts"
    # Venue rule: a generic title at a known dojo still files under Martial Arts.
    assert _class_subgroup("Fundamentals", "Bridge City BJJ") == "Martial Arts"
    assert _class_subgroup("Adult Program", "Bridge City Brazilian Jiu-Jitsu") == "Martial Arts"


def test_pool_classes_get_aquatic_fitness_subsection() -> None:
    for title in ("Lap Swim", "Water Aerobics", "Aqua Zumba", "Deep Water Fitness"):
        assert _class_subgroup(title) == "Aquatic fitness", title
    # A dryland Zumba class still files under Strength & Cardio (no aqua signal).
    assert _class_subgroup("Zumba") == "Strength & Cardio"
