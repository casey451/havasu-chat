"""E-1 / calendar redesign — events-list buckets are honest, contiguous, gap-free.

Today / This Weekend / This Week / Next Week are disjoint and together tile
every day from today through the end of next week. The P0 this guards: the old
layout left Saturday/Sunday in a gap ("This Week" effectively ended Friday,
"Next Week" started Monday), so weekend events silently vanished from the list.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.home.router import _event_list_windows

_BUCKETS = ("today", "this_week", "weekend", "next_week")


def _d(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 12, 0)


def _covered_days(w: dict) -> list[date]:
    """Every calendar day covered by any bucket (collapsed spans cover none)."""
    out: list[date] = []
    for key in _BUCKETS:
        start, end = w[key]
        d = start.date()
        while d <= end.date():
            out.append(d)
            d += timedelta(days=1)
    return out


def test_wednesday_buckets_split_week_and_weekend() -> None:
    # 2026-06-03 is a Wednesday.
    w = _event_list_windows(_d(2026, 6, 3))
    assert w["today"] == (_d(2026, 6, 3), _d(2026, 6, 3))
    # This week runs tomorrow (Thu) through Friday — the weekend is its own bucket.
    assert w["this_week"][0].date().isoformat() == "2026-06-04"
    assert w["this_week"][1].date().isoformat() == "2026-06-05"
    # This weekend is the upcoming Sat+Sun.
    assert w["weekend"][0].date().isoformat() == "2026-06-06"
    assert w["weekend"][1].date().isoformat() == "2026-06-07"
    # Next week is Mon Jun 8 .. Sun Jun 14.
    assert w["next_week"][0].date().isoformat() == "2026-06-08"
    assert w["next_week"][1].date().isoformat() == "2026-06-14"


def test_every_day_lands_in_exactly_one_bucket() -> None:
    """No gap, no double-listing, from any anchor weekday (Mon..Sun)."""
    for day in range(1, 8):  # 2026-06-01 (Mon) .. 2026-06-07 (Sun)
        now = _d(2026, 6, day)
        w = _event_list_windows(now)
        covered = _covered_days(w)
        assert len(covered) == len(set(covered)), f"buckets overlap for {now.date()}"
        horizon_end = w["next_week"][1].date()
        expected: list[date] = []
        d = now.date()
        while d <= horizon_end:
            expected.append(d)
            d += timedelta(days=1)
        assert sorted(covered) == expected, f"coverage gap for {now.date()}"


def test_saturday_and_sunday_never_fall_in_a_gap() -> None:
    """The P0: midweek, the upcoming Sat+Sun belong to This Weekend only."""
    w = _event_list_windows(_d(2026, 6, 3))  # Wednesday
    sat, sun = date(2026, 6, 6), date(2026, 6, 7)
    assert w["weekend"][0].date() <= sat <= w["weekend"][1].date()
    assert w["weekend"][0].date() <= sun <= w["weekend"][1].date()
    # ... and NOT to This Week or Next Week.
    assert not (w["this_week"][0].date() <= sat <= w["this_week"][1].date())
    assert not (w["next_week"][0].date() <= sun <= w["next_week"][1].date())


def test_on_saturday_today_keeps_sat_and_weekend_holds_sunday() -> None:
    w = _event_list_windows(_d(2026, 6, 6))  # Saturday
    assert w["today"][0].date().isoformat() == "2026-06-06"
    assert w["weekend"][0].date().isoformat() == "2026-06-07"
    assert w["weekend"][1].date().isoformat() == "2026-06-07"
    # No weekdays remain before Saturday: this_week collapses (start > end).
    assert w["this_week"][0].date() > w["this_week"][1].date()


def test_on_sunday_weekend_and_this_week_collapse_empty() -> None:
    # Sunday's own events live in "today"; the weekend bucket has nothing left.
    w = _event_list_windows(_d(2026, 6, 7))  # Sunday
    assert w["weekend"][0].date() > w["weekend"][1].date()
    assert w["this_week"][0].date() > w["this_week"][1].date()
    assert w["next_week"][0].date().isoformat() == "2026-06-08"
    assert w["next_week"][1].date().isoformat() == "2026-06-14"
