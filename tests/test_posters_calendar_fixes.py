"""FIX_POSTERS_AND_CALENDAR — items 2 & 3 (lake calendar surface).

Item 2: the home "Full calendar" button lands on the week view.
Item 3: ``swipe_weeks`` builder + the lake events-ui renders a swipeable-week
carousel and a simplified Day / Full-calendar mobile toggle, while the desktop
month grid still renders. (The desert month-grid markup is covered separately in
tests/test_events_ui_views.py; the live site is lake-default.)
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.home import events_views
from app.main import app


def test_home_calendar_button_points_to_calendar() -> None:
    # v4 (flag collapsed 2026-07-02): the week strip's Calendar button targets
    # the v4 /calendar month grid, not the legacy week view.
    body = TestClient(app).get("/home").text
    assert 'class="calbtn" href="/calendar"' in body


def test_swipe_weeks_builder_shape_and_today_flagging() -> None:
    today = date(2099, 7, 15)  # a Wednesday
    with SessionLocal() as db:
        weeks = events_views.swipe_weeks(db, today=today, num_weeks=5)
    assert len(weeks) == 5
    # Each week is a full Sun–Sat set of 7 day rows.
    for wk in weeks:
        assert len(wk["days"]) == 7
        assert date.fromisoformat(wk["start_iso"]).weekday() == 6  # Sunday (Mon=0)
    # Exactly the week containing today is flagged current, and only that day is
    # marked is_today (week_rows' first-row "Today" must be corrected by date).
    current = [wk for wk in weeks if wk["is_current"]]
    assert len(current) == 1
    today_days = [d for wk in weeks for d in wk["days"] if d["is_today"]]
    assert len(today_days) == 1 and today_days[0]["iso"] == today.isoformat()
    # The first week is the week of today; consecutive weeks step by 7 days.
    starts = [date.fromisoformat(wk["start_iso"]) for wk in weeks]
    assert starts[0] == today - timedelta(days=(today.weekday() + 1) % 7)
    assert all(starts[i + 1] - starts[i] == timedelta(days=7) for i in range(4))


def test_lake_week_view_is_the_v4_day_list() -> None:
    # v4.5 PR-1: the events-ui week view is the v4 seven-day .ev list (the old
    # swipe carousel + Day/Full mobile toggle were dropped for the single v4
    # language — mobile scrolls the same list, matching /calendar). See PROGRESS.
    body = TestClient(app).get("/events-ui?view=week&theme=lake").text
    assert "This week" in body
    assert "wklist" in body
    assert re.search(r'href="/events-ui\?date=\d{4}-\d{2}-\d{2}"', body)


def test_lake_month_view_is_the_v4_grid() -> None:
    body = TestClient(app).get("/events-ui?view=month&theme=lake&cal=2099-07").text
    assert "July 2099" in body
    # v4 month grid: a Sunday-anchored header and a full set of day cells (≥28 —
    # links on days with events, plain cells otherwise). Dots on mobile, no swipe.
    assert 'class="calmonth"' in body
    assert "<span>Sun</span>" in body
    assert body.count('class="cell') >= 28
