"""Past/upcoming determination is computed in America/Phoenix and agrees across
surfaces (home feed, /events-ui, event-detail "passed" banner).

Regression for the 2026-06-21 live bug: the 1 PM "Motor Madness" event (stored
with a 00:00 / midnight end_time by the allevents source) was marked "passed" at
08:54 local — ~4 hours before it started — while the same-day 11 AM and 12 PM
events (real end_times) were correct. Root cause was NOT a uniform UTC offset
(``now`` was already Phoenix everywhere) but the midnight end_time being treated
as 00:00 *that morning* instead of the following midnight. The shared
:func:`occurrence_end_dt` helper now resolves the cross-midnight end for every
surface, so they can't disagree.

``now`` is frozen deterministically in America/Phoenix; no wall-clock reliance.
"""

from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.core.timezone import occurrence_end_dt, to_lake_naive
from app.home.events_views import _occurrence_expired
from app.main import _event_is_past

PHX = ZoneInfo("America/Phoenix")
UTC = ZoneInfo("UTC")

DAY = date(2026, 6, 21)
# 08:54 local — the moment in the bug report (Motor Madness still 4h out).
NOW_0854 = datetime(2026, 6, 21, 8, 54, tzinfo=PHX)


def _ev(**kw):
    base = dict(
        date=DAY,
        start_time=time(10, 0),
        end_date=None,
        end_time=None,
        rdate=None,
        rrule=None,
        is_recurring=False,
        exdate=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- occurrence_end_dt: the shared end-moment resolver ---------------------
def test_end_dt_midnight_end_wraps_to_next_day():
    # 1 PM start, 00:00 end == ends at the FOLLOWING midnight, not this morning.
    assert occurrence_end_dt(DAY, time(13, 0), time(0, 0)) == datetime(2026, 6, 22, 0, 0)


def test_end_dt_end_before_start_wraps():
    # 10 PM–2 AM crosses midnight.
    assert occurrence_end_dt(DAY, time(22, 0), time(2, 0)) == datetime(2026, 6, 22, 2, 0)


def test_end_dt_normal_same_day():
    assert occurrence_end_dt(DAY, time(11, 0), time(19, 0)) == datetime(2026, 6, 21, 19, 0)


def test_end_dt_no_end_uses_default_run():
    assert occurrence_end_dt(DAY, time(10, 0), None, default_minutes=120) == datetime(
        2026, 6, 21, 12, 0
    )


def test_end_dt_fully_tbd_is_none():
    assert occurrence_end_dt(DAY, None, None) is None


# --- Motor Madness scenario: upcoming on BOTH surfaces ---------------------
def test_detail_banner_motor_madness_not_passed():
    ev = _ev(start_time=time(13, 0), end_time=time(0, 0))
    with patch("app.main.now_lake_havasu", return_value=NOW_0854):
        assert _event_is_past(ev) is False


def test_feed_muting_motor_madness_not_past():
    assert _occurrence_expired(DAY, time(13, 0), time(0, 0), NOW_0854) is False


def test_event_later_today_is_upcoming_earlier_today_is_past():
    # later today -> upcoming
    assert _occurrence_expired(DAY, time(13, 0), time(15, 0), NOW_0854) is False
    # earlier today, finished well over the grace window -> past
    assert _occurrence_expired(DAY, time(5, 0), time(6, 0), NOW_0854) is True
    with patch("app.main.now_lake_havasu", return_value=NOW_0854):
        assert _event_is_past(_ev(start_time=time(5, 0), end_time=time(6, 0))) is True


# --- feed and detail banner AGREE for the same event -----------------------
def _both_surfaces(start_t, end_t, now):
    feed_past = _occurrence_expired(DAY, start_t, end_t, now)
    with patch("app.main.now_lake_havasu", return_value=now):
        detail_past = _event_is_past(_ev(start_time=start_t, end_time=end_t))
    return feed_past, detail_past


def test_feed_and_detail_agree():
    # upcoming midnight-end event: both say not-past (the bug made detail disagree)
    assert _both_surfaces(time(13, 0), time(0, 0), NOW_0854) == (False, False)
    # clearly-finished event (well past the feed grace window): both say past
    assert _both_surfaces(time(5, 0), time(6, 0), NOW_0854) == (True, True)
    # still-running event: both say not-past
    assert _both_surfaces(time(8, 0), time(17, 0), NOW_0854) == (False, False)


# --- naive vs tz-aware "now" at the same Havasu wall-clock are identical ----
def test_now_tz_aware_utc_equals_phoenix_equals_naive():
    same_instant_utc = datetime(2026, 6, 21, 15, 54, tzinfo=UTC)  # == 08:54 Phoenix
    naive_phx_walltime = datetime(2026, 6, 21, 8, 54)  # naive treated as Phoenix
    for start_t, end_t in [(time(13, 0), time(0, 0)), (time(5, 0), time(6, 0))]:
        a = _occurrence_expired(DAY, start_t, end_t, NOW_0854)
        b = _occurrence_expired(DAY, start_t, end_t, same_instant_utc)
        c = _occurrence_expired(DAY, start_t, end_t, naive_phx_walltime)
        assert a == b == c, (start_t, end_t, a, b, c)


def test_to_lake_naive_converts_and_passes_through():
    assert to_lake_naive(datetime(2026, 6, 21, 15, 54, tzinfo=UTC)) == datetime(2026, 6, 21, 8, 54)
    assert to_lake_naive(datetime(2026, 6, 21, 8, 54, tzinfo=PHX)) == datetime(2026, 6, 21, 8, 54)
    assert to_lake_naive(datetime(2026, 6, 21, 8, 54)) == datetime(2026, 6, 21, 8, 54)
