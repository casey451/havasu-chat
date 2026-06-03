"""E-1 — events-list buckets are honest, contiguous, and gap-free."""

from __future__ import annotations

from datetime import datetime

from app.home.router import _event_list_windows


def _d(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 12, 0)


def test_wednesday_weekend_not_mislabeled() -> None:
    # 2026-06-03 is a Wednesday. The old code put Thu/Fri/Sat under "This Weekend".
    w = _event_list_windows(_d(2026, 6, 3))
    assert w["today"] == (_d(2026, 6, 3), _d(2026, 6, 3))
    # This week runs tomorrow (Thu Jun 4) through Sunday Jun 7.
    assert w["this_week"][0] == _d(2026, 6, 4)
    assert w["this_week"][1].date().isoformat() == "2026-06-07"
    # Next week is Mon Jun 8 .. Sun Jun 14 — Saturday is NOT in "Next Week".
    assert w["next_week"][0].date().isoformat() == "2026-06-08"
    assert w["next_week"][1].date().isoformat() == "2026-06-14"


def test_windows_are_contiguous_and_disjoint() -> None:
    for day in range(1, 8):
        w = _event_list_windows(_d(2026, 6, day))
        today_end = w["today"][1].date()
        tw_start, tw_end = w["this_week"][0].date(), w["this_week"][1].date()
        nw_start, nw_end = w["next_week"][0].date(), w["next_week"][1].date()
        # this_week starts the day after today; next_week starts the day after this_week.
        assert (tw_start - today_end).days == 1
        assert (nw_start - tw_end).days == 1
        # next_week is a full 7-day span.
        assert (nw_end - nw_start).days == 6


def test_sunday_collapses_this_week_to_empty_span() -> None:
    # On a Sunday, "this week" already ends today, so its span is empty (start > end);
    # the query simply returns nothing rather than mislabeling next week's days.
    w = _event_list_windows(_d(2026, 6, 7))  # Sunday
    assert w["this_week"][0].date() > w["this_week"][1].date()
    assert w["next_week"][0].date().isoformat() == "2026-06-08"
