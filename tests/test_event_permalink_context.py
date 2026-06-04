"""Event permalink handler context: is_past banner + NULL-time formatting.

Follow-up to WP-3/WP-4: the event_permalink.html template references `is_past`
(the "This event has passed" banner) but the main.py handler never passed it,
so the banner was dead. WP-4 also allows NULL event times at ingest, which would
500 the old `_format_event_datetime` (it dereferenced start_time unconditionally).
These tests pin both fixes. The helpers read only attributes, so a lightweight
namespace stands in for an Event row -- no DB, no shared-session pollution.
"""

from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.main import _event_is_past, _format_event_datetime

PHX = ZoneInfo("America/Phoenix")
# Thursday, June 4 2026, noon local -- fixed reference for deterministic cases.
REF = datetime(2026, 6, 4, 12, 0, tzinfo=PHX)


def _ev(**kw):
    base = dict(
        date=date(2026, 6, 4),
        start_time=time(10, 0),
        end_date=None,
        end_time=None,
        rdate=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_format_datetime_with_time():
    assert _format_event_datetime(_ev(start_time=time(10, 30))) == "Thursday, June 4, 10:30 AM"


def test_format_datetime_null_time_does_not_crash():
    # WP-4 NULL time -- date only, no fabricated time, no AttributeError.
    out = _format_event_datetime(_ev(start_time=None))
    assert out == "Thursday, June 4"


def test_is_past_one_off_yesterday_is_past():
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 3))) is True


def test_is_past_one_off_tomorrow_is_not_past():
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 5))) is False


def test_is_past_today_time_already_passed():
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=time(10, 0))) is True


def test_is_past_today_time_still_upcoming():
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=time(14, 0))) is False


def test_is_past_today_date_only_not_buried_midday():
    # A same-day all-day event (NULL time) is not "passed" mid-day.
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=None)) is False


def test_is_past_recurring_series_never_past():
    # rdate present -> recurring; the series is not "passed" even on an old date.
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 3), rdate=["2026-06-03"])) is False


def test_is_past_uses_end_date_when_event_spans_into_future():
    with patch("app.main.now_lake_havasu", return_value=REF):
        ev = _ev(date=date(2026, 6, 3), end_date=date(2026, 6, 6))
        assert _event_is_past(ev) is False
