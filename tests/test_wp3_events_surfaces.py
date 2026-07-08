"""WP-3 — events list windows, series grouping, Tonight selector, calendar, ics."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import sandstone

# (the pre-v4 window-feed/tonight-card builders were deleted 2026-07-02 with
# the HOME_REDESIGN flag collapse; the live surfaces below are /events-ui and
# the sandstone month calendar)
from app.main import app

_LHC = ZoneInfo("America/Phoenix")


def _add_event(
    db,
    *,
    title: str,
    on,
    start: time,
    loc: str,
    end: time | None = None,
    tags=None,
    recurring: bool = False,
) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=end,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=tags or [],
        status="live",
        source="test-wp3",
        verified=True,
        is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.id, ev.entity_id


# --- window cap + honest total ---------------------------------------------




# --- series grouped by venue ------------------------------------------------



# --- Tonight selector (DL-16) ----------------------------------------------


def _fixed_now() -> datetime:
    # 2099-03-10 17:00 local — far from seeded rows.
    return datetime(2099, 3, 10, 17, 0, tzinfo=_LHC)





# --- home calendar: one-off pills prioritised, count + iso ------------------


def test_calendar_cell_carries_iso_and_count_and_prioritises_oneoffs() -> None:
    eids: list[str] = []
    # Use a quiet future month so seeded data does not pollute the day under test.
    year, month, day = 2099, 4, 12
    from datetime import date as _date

    with SessionLocal() as db:
        # 3 recurring classes + 1 special one-off on the same day. Only the
        # one-off (special) should win a visible pill slot; classes overflow.
        for i in range(3):
            _id, eid = _add_event(
                db,
                title=f"ZZ Class {i}",
                on=_date(year, month, day),
                start=time(5, 0),
                loc="Pool",
                recurring=True,
                tags=["class"],
            )
            eids.append(eid)
        _id, eid = _add_event(
            db,
            title="ZZ Big Festival",
            on=_date(year, month, day),
            start=time(18, 0),
            loc="Bridge",
            tags=["festival"],
        )
        eids.append(eid)
        db.commit()
    try:
        with SessionLocal() as db:
            cal = sandstone.calendar_month(db, year=year, month=month, today=_date(2099, 4, 1))
        cell = next(
            c
            for week in cal["weeks"]
            for c in week
            if c.get("in_month") and c.get("day") == day
        )
        assert cell["iso"] == "2099-04-12"
        # The count is one-off events only; the 3 recurring classes collapse
        # into the class badge instead of inflating the cell.
        assert cell["count"] == 1
        assert cell["class_count"] == 3
        # The special one-off must be among the visible pills.
        visible_titles = [e["title"] for e in cell["events"]]
        assert "ZZ Big Festival" in visible_titles
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


# --- /events-ui rendering + ?view= / ?when= / ?date= -------------------------


def test_events_ui_renders_view_toggle_and_today_accordion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a weekday, the default /events-ui is the TODAY view: a no-JS
    Today|Week|Month toggle plus the labelled today section. (WS9c makes Fri–Sun
    default to the This-weekend span, so the clock is pinned to a Monday to test
    the weekday default deterministically.) Seeds one all-day happening for that
    day so the events-only Calendar has a group to render."""
    monday = datetime(2099, 3, 9, 9, 0, tzinfo=_LHC)  # a Monday
    monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: monday)
    today = monday.date()
    title = f"ZZ Toggle Probe Festival {uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        eid, _ent = _add_event(db, title=title, on=today, start=time(0, 0), loc="Beach",
                               tags=["festival"])
        db.commit()
    try:
        with TestClient(app) as client:
            body = client.get("/events-ui").text
        assert 'aria-label="Calendar view"' in body  # view toggle present
        assert "?view=week" in body and "?view=month" in body
        # Today view is the default: the Today tab is current, the accordion renders.
        assert 'aria-current="page"><span class="cl">Today</span>' in body
        assert 'class="sec' in body  # today section accordion (seeded happening)
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.id == eid))
            db.commit()


def test_events_ui_when_today_maps_to_today_view() -> None:
    """Legacy ?when=today still narrows to today only (now the Today view)."""
    with TestClient(app) as client:
        body = client.get("/events-ui?when=today").text
    assert 'aria-current="page"><span class="cl">Today</span>' in body  # Today view current
    assert 'wklist' not in body  # not the week view


def test_events_ui_when_weekend_still_responds_with_week_view() -> None:
    """Legacy ?when=weekend (and the other old chips) must keep answering:
    they map to the Week view, which tiles the upcoming days gap-free."""
    with TestClient(app) as client:
        for legacy in ("weekend", "this-week", "next-week", "all"):
            resp = client.get(f"/events-ui?when={legacy}")
            assert resp.status_code == 200
            assert 'wklist' in resp.text


def test_events_ui_date_deeplink_shows_single_day() -> None:
    with TestClient(app) as client:
        body = client.get("/events-ui?date=2099-04-12").text
    assert "Sunday, April 12" in body  # the single-day H1
    assert 'class="evnav"' in body  # day navigation strip
    assert "/events-ui?date=2099-04-11" in body  # prev-day link
    assert "/events-ui?date=2099-04-13" in body  # next-day link


def test_events_ui_weekend_events_never_fall_in_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0 regression, carried over from the bucket era: weekend events must
    never vanish in a window gap. The lake Week view renders an upcoming list
    from today, so the upcoming Saturday and Sunday both surface, and any day
    stays reachable on its ?date= page (the month grid links every date).
    """
    suffix = uuid.uuid4().hex[:6]
    eids: list[str] = []
    monday = datetime(2099, 8, 24, 9, 0, tzinfo=_LHC)  # quiet far-future Monday
    assert monday.weekday() == 0
    saturday = monday.date() + timedelta(days=5)
    sunday = monday.date() + timedelta(days=6)
    next_saturday = saturday + timedelta(days=7)
    sat_title = f"ZZ Sat Regatta {suffix}"
    sun_title = f"ZZ Sun Brunch {suffix}"
    next_sat_title = f"ZZ NextSat Derby {suffix}"
    with SessionLocal() as db:
        for title, on in (
            (sat_title, saturday),
            (sun_title, sunday),
            (next_sat_title, next_saturday),
        ):
            _id, eid = _add_event(db, title=title, on=on, start=time(10, 0), loc="Beach")
            eids.append(eid)
        db.commit()
    try:
        monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: monday)
        with TestClient(app) as client:
            week_body = client.get("/events-ui?view=week").text
            day_body = client.get(f"/events-ui?date={next_saturday.isoformat()}").text
        assert sat_title in week_body  # the Saturday event surfaces — no gap
        assert sun_title in week_body  # the Sunday event surfaces — no gap
        assert next_sat_title in day_body  # reachable on its day page
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


def test_event_detail_renders_lake_with_description() -> None:
    eids: list[str] = []
    start = now_lake_havasu()
    with SessionLocal() as db:
        _id, eid = _add_event(
            db, title="ZZ Detail Font", on=start.date() + timedelta(days=1), start=time(18, 0), loc="Bridge"
        )
        eids.append(eid)
        db.commit()
    try:
        with TestClient(app) as client:
            resp = client.get(f"/events/{_id}")
        assert resp.status_code == 200
        body = resp.text
        # v4.6 PR-1: the event permalink rides the standalone v4 shell.
        assert 'data-theme="lake"' in body
        assert "/static/styles/lake_redesign.css" in body
        # pre-line description container is present.
        assert "evd-desc" in body
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


# --- /events.ics feed -------------------------------------------------------


def _ics_client() -> TestClient:
    # The /events.ics router is registered in app.main as a PR follow-up (main.py
    # is owned by WP-7); mount it on a throwaway app so the feed is testable now.
    from fastapi import FastAPI

    from app.api.routes.calendar_feed import router as calendar_feed_router

    test_app = FastAPI()
    test_app.include_router(calendar_feed_router)
    return TestClient(test_app)


def test_events_ics_feed_is_valid_icalendar() -> None:
    eids: list[str] = []
    start = now_lake_havasu()
    day = start.date() + timedelta(days=2)
    with SessionLocal() as db:
        _id, eid = _add_event(
            db,
            title="ZZ ICS One-off; with, commas",
            on=day,
            start=time(18, 0),
            end=time(20, 0),
            loc="London Bridge",
        )
        eids.append(eid)
        rec_id, eid = _add_event(
            db, title="ZZ ICS Recurring", on=day, start=time(7, 0), loc="Pool", recurring=True
        )
        eids.append(eid)
        ev = db.query(Event).filter(Event.id == rec_id).first()
        ev.rrule = "FREQ=WEEKLY;BYDAY=MO"
        db.commit()
    try:
        with _ics_client() as client:
            resp = client.get("/events.ics")
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers.get("content-type", "")
        body = resp.text
        assert body.startswith("BEGIN:VCALENDAR\r\n")
        assert body.rstrip().endswith("END:VCALENDAR")
        assert "VERSION:2.0" in body
        assert body.count("BEGIN:VEVENT") == body.count("END:VEVENT") >= 2
        # commas/semicolons in SUMMARY are escaped
        assert "SUMMARY:ZZ ICS One-off\\; with\\, commas" in body
        # recurring event carries its RRULE
        assert "RRULE:FREQ=WEEKLY;BYDAY=MO" in body
        # WS5/B5: timed events carry an explicit America/Phoenix TZID (not floating
        # local time) plus a VTIMEZONE, so out-of-zone subscribers see the right hour.
        assert "BEGIN:VTIMEZONE" in body and "TZID:America/Phoenix" in body
        assert "DTSTART;TZID=America/Phoenix:" in body
        assert "DTEND;TZID=America/Phoenix:" in body
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()
