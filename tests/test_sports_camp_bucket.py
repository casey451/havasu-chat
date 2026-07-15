"""A multi-day sports camp buckets into Fitness & Sports (Casey 2026-07-14).

A dated sports camp (e.g. Split Finger's "Softball Summer Session … — Camp") is a
non-recurring one-off, so it used to fall through group_for_tier to "Things to
Do". It's really a Fitness & Sports program. The gate is narrow — BOTH a sports
AND a camp tag — so non-sports camps (VBS) and one-off sports events (races) stay
put.
"""

from __future__ import annotations

from app.home.event_buckets import TIER_OTHER, _is_sports_camp, group_for_tier
from app.home.sandstone import _event_tier


def test_sports_camp_routes_to_fitness_and_sports() -> None:
    b = group_for_tier(
        TIER_OTHER, recurring=False,
        title="Softball Summer Session #2 (Ages 7-12) — Camp",
        tags=["sports", "youth", "camp"],
    )
    assert b == "classes"  # "Fitness & Sports"


def test_full_pipeline_softball_camp() -> None:
    title = "Softball Summer Session #2 (Ages 7-12) — Camp"
    tags = ["sports", "youth", "camp"]
    tier = _event_tier(title=title, tags=tags, featured=False, recurring=False)
    assert group_for_tier(tier, recurring=False, title=title, tags=tags) == "classes"


def test_vbs_camp_without_sports_tag_not_swept_in() -> None:
    # Camp tag but no sports tag: a church/VBS camp stays out of Fitness & Sports.
    b = group_for_tier(
        TIER_OTHER, recurring=False,
        title="Vacation Bible School Camp", tags=["family", "youth", "camp"],
    )
    assert b == "events"


def test_one_off_sports_event_without_camp_tag_unchanged() -> None:
    # Sports tag but no camp tag: a one-off race/game is still "Things to Do".
    b = group_for_tier(
        TIER_OTHER, recurring=False, title="Turkey Trot 5K", tags=["sports"],
    )
    assert b == "events"


def test_is_sports_camp_predicate() -> None:
    assert _is_sports_camp(["sports", "camp"]) is True
    assert _is_sports_camp(["Sports", "Camp"]) is True  # case-insensitive
    assert _is_sports_camp(["sports"]) is False
    assert _is_sports_camp(["camp"]) is False
    assert _is_sports_camp([]) is False
    assert _is_sports_camp(None) is False
