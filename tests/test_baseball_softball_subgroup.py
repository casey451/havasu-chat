"""Baseball & Softball is its own Fitness & Sports subgroup (Casey 2026-07-15).

All Split Finger Athletics classes file here regardless of title (venue-force,
like the martial-arts dojo rule); baseball/softball titles from any venue file
here too (split out of Sports & Racing). The slug lands in the Fitness & Sports
("classes") top-level bucket.
"""

from __future__ import annotations

from app.events.activity_taxonomy import (
    BASEBALL_LABEL,
    SUBGROUP_ORDER,
    SUBGROUP_SLUGS,
    activity_bucket,
    classify_activity,
    classify_class_subgroup,
    resolve_activity,
)

_SF = "Split Finger Athletics"


def test_taxonomy_wiring() -> None:
    assert SUBGROUP_SLUGS[BASEBALL_LABEL] == "baseball"
    assert BASEBALL_LABEL in SUBGROUP_ORDER
    # A SUBGROUP_SLUGS value auto-maps to the Fitness & Sports bucket.
    assert activity_bucket("baseball") == "classes"


def test_split_finger_venue_force_all_classes() -> None:
    # Every Split Finger class files under Baseball & Softball, even non-baseball titles.
    for title in ("Strength/Conditioning/Agility", "Team Speed & Agility", "TRX & Tabata w/Toree"):
        assert classify_class_subgroup(title, _SF) == BASEBALL_LABEL, title
        assert classify_activity(title, _SF) == "baseball", title
        assert resolve_activity(title, _SF) == "baseball", title


def test_split_finger_softball_camp() -> None:
    assert classify_class_subgroup("Softball Summer Session #2 (Ages 7-12) — Camp", _SF) == BASEBALL_LABEL
    assert classify_activity("Softball Summer Session #2 (Ages 7-12) — Camp", _SF) == "baseball"


def test_baseball_softball_title_from_any_venue() -> None:
    # Split out of Sports & Racing: a baseball/softball title types here anywhere.
    assert classify_class_subgroup("Youth Baseball Clinic", "City Park") == BASEBALL_LABEL
    assert classify_class_subgroup("Adult Softball League", "Rotary Park") == BASEBALL_LABEL


def test_non_split_finger_strength_class_unchanged() -> None:
    # The venue-force is narrow: a strength class elsewhere is still Strength & Cardio.
    assert classify_class_subgroup("Strength/Conditioning", "Havasu CrossFit") == "Strength & Cardio"


def test_other_sports_still_sports_and_racing() -> None:
    # Non-baseball sports keep their Sports & Racing home.
    assert classify_class_subgroup("Youth Basketball", "City Gym") == "Sports & Racing"
    assert classify_class_subgroup("BMX Race Night", "SARA Park") == "Sports & Racing"
