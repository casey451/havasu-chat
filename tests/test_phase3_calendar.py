"""Phase 3 (calendar & classes) — unit tests for the auto-expiry helper."""

from __future__ import annotations

from datetime import date, datetime, time

from app.home.events_views import (
    _class_subgroup,
    _occurrence_expired,
    _row_time_label,
    _split_class_subgroups,
)

_TODAY = date(2026, 6, 16)
_NOW = datetime(2026, 6, 16, 16, 30)  # 4:30 PM


def test_morning_class_expired_in_afternoon() -> None:
    # 9 AM start; >1h ago by 4:30 PM -> expired (start-based cutoff).
    assert _occurrence_expired(_TODAY, time(9, 0), None, _NOW) is True


def test_within_first_hour_not_expired() -> None:
    # Started 4:00 PM; 4:30 is only 30 min in, still within the first hour.
    assert _occurrence_expired(_TODAY, time(16, 0), time(18, 0), _NOW) is False


def test_started_over_an_hour_ago_expired_even_if_still_running() -> None:
    # 3 PM start, 6 PM end: still running at 4:30, but started >1h ago, so the
    # start-based cutoff drops it from the list anyway.
    assert _occurrence_expired(_TODAY, time(15, 0), time(18, 0), _NOW) is True


def test_evening_event_not_expired() -> None:
    assert _occurrence_expired(_TODAY, time(18, 0), None, _NOW) is False


def test_time_tbd_never_expires() -> None:
    assert _occurrence_expired(_TODAY, None, None, _NOW) is False


def test_all_day_event_never_expires_on_today() -> None:
    # All-day events (start 00:00, no end) must survive the Today view all day:
    # the 2h default would otherwise place their end at ~2 AM and purge them.
    # Regression: pickleball Open Play (loaded as all-day) vanished from Today
    # by ~3 AM while still showing on future days and in the .ics feed.
    assert _occurrence_expired(_TODAY, time(0, 0), None, _NOW) is False
    # Even late at night it stays.
    assert (
        _occurrence_expired(_TODAY, time(0, 0), None, datetime(2026, 6, 16, 23, 59))
        is False
    )


def test_midnight_event_with_explicit_end_still_expires() -> None:
    # A real (non-all-day) occurrence that genuinely ends at 00:30 is NOT
    # all-day (it has an end_time), so the normal expiry path still applies.
    assert _occurrence_expired(_TODAY, time(0, 0), time(0, 30), _NOW) is True


def test_other_days_never_expire() -> None:
    assert _occurrence_expired(date(2026, 6, 17), time(9, 0), None, _NOW) is False
    assert _occurrence_expired(date(2026, 6, 15), time(9, 0), None, _NOW) is False


def test_no_now_is_noop() -> None:
    assert _occurrence_expired(_TODAY, time(9, 0), None, None) is False


def test_class_subgroup_classifier() -> None:
    assert _class_subgroup("Amalaya Hot Yoga") == "Yoga"
    assert _class_subgroup("Beginner Reformer Pilates") == "Pilates"
    assert _class_subgroup("Adult No-Gi") == "Martial Arts"
    assert _class_subgroup("Adult MMA") == "Martial Arts"
    assert _class_subgroup("Pre-Ballet / Pre-Tap") == "Dance"
    assert _class_subgroup("Rec Tumbling L1-3") == "Gymnastics"
    assert _class_subgroup("Sculpt") == "Strength & Cardio"
    assert _class_subgroup("Spin") == "Strength & Cardio"
    assert _class_subgroup("Riding Lessons") == "Other classes"


def test_split_class_subgroups_orders_and_omits_empty() -> None:
    rows = [
        {"title": "Morning Yoga"},
        {"title": "Reformer Pilates"},
        {"title": "Adult MMA"},
        {"title": "Riding Lessons"},
    ]
    subs = _split_class_subgroups(rows)
    # Phase 1: martial arts is wrapped under a "Martial arts" subgroup (its
    # disciplines/youth nest as children); the others stay flat activity nodes.
    assert [s["label"] for s in subs] == ["Yoga", "Pilates", "Martial arts", "Other classes"]
    assert all(s["count"] == 1 for s in subs)


# The old _family_subgroup / _split_family_subgroups vocabulary (Kids & Family
# overlay) was retired 2026-06-26 — youth items now peel into a "Youth <activity>"
# sub of their own group (covered by tests/test_calendar_taxonomy_phase7.py).


def test_pickleball_gets_its_own_subgroup() -> None:
    assert (
        _class_subgroup("Pickleball Open Play – The Ark Center") == "Pickleball"
    )
    assert _class_subgroup("Pickleball Open Play") == "Pickleball"
    # A non-pickleball activity still lands by its real type.
    assert _class_subgroup("Adult MMA") == "Martial Arts"


def test_row_time_label_all_day_only_for_open_play() -> None:
    # Known time renders normally.
    assert _row_time_label("Pickleball Open Play", time(8, 0), time(10, 0)) == "8 AM"
    # All-day open play (00:00 / no end) reads "All day", not "Time TBD".
    assert _row_time_label("Pickleball Open Play – Ark", time(0, 0), None) == "All day"
    # A generic unknown-time event keeps the honest "Time TBD" (no false "All day").
    assert _row_time_label("Community Potluck", time(0, 0), None) == "Time TBD"
    assert _row_time_label("Community Potluck", None, None) == "Time TBD"
