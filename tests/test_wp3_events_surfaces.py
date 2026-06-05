"""WP-3 — events list windows, series grouping, Tonight selector, calendar, ics."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import sandstone
from app.home.router import (
    _WINDOW_CAP,
    _events_for_window_with_total,
    _group_series_by_venue,
    _tonight_card,
)
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


def test_window_total_counts_collapsed_rows_beyond_cap() -> None:
    suffix = uuid.uuid4().hex[:6]
    eids: list[str] = []
    start = now_lake_havasu()
    day = start.date()
    win = datetime.combine(day, time(12, 0))
    with SessionLocal() as db:
        # More distinct one-offs than the cap so total > shown.
        for i in range(_WINDOW_CAP + 5):
            _id, eid = _add_event(
                db,
                title=f"ZZ WP3 oneoff {suffix} {i}",
                on=day,
                start=time(9, 0),
                loc=f"Venue {i}",
            )
            eids.append(eid)
        db.commit()
    try:
        with SessionLocal() as db:
            rows, total = _events_for_window_with_total(
                db, start_day=win, end_day=win, limit=_WINDOW_CAP
            )
        assert total >= _WINDOW_CAP + 5
        assert len(rows) == _WINDOW_CAP  # capped at the limit
        assert total > len(rows)  # honest: more exist than shown
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


def test_oneoffs_fill_before_recurring_under_cap() -> None:
    # A featured recurring class must not crowd a plain one-off out of the cap.
    #
    # xdist isolation (T2.4): the window is a far-future week (like the
    # ``_fixed_now`` Tonight tests below) instead of the real current week.
    # With ``limit=2`` any other test's live rows in the queried window evict
    # this test's rows from the capped result, so the window must contain
    # only rows this test seeded.
    suffix = uuid.uuid4().hex[:6]
    eids: list[str] = []
    monday = datetime(2099, 9, 7).date()  # far-future Monday, unused elsewhere
    win = datetime.combine(monday, time(0, 0))
    with SessionLocal() as db:
        # Recurring series (5 days), all one venue.
        for d in range(5):
            _id, eid = _add_event(
                db,
                title=f"ZZ Class {suffix}",
                on=monday + timedelta(days=d),
                start=time(5, 0),
                loc="Aquatic Center",
            )
            eids.append(eid)
        # One plain one-off.
        _id, eid = _add_event(
            db, title=f"ZZ Gala {suffix}", on=monday, start=time(18, 0), loc="Bridge"
        )
        eids.append(eid)
        db.commit()
    try:
        with SessionLocal() as db:
            rows, _ = _events_for_window_with_total(
                db, start_day=win, end_day=win + timedelta(days=6), limit=2
            )
        titles = [r["title"] for r in rows]
        # With a tiny cap of 2, the one-off must survive (it sorts before the class).
        assert f"ZZ Gala {suffix}" in titles
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


# --- series grouped by venue ------------------------------------------------


def test_group_series_by_venue_buckets_and_preserves_order() -> None:
    ongoing = [
        {"title": "Lap Swim", "venue": "Aquatic Center"},
        {"title": "Water Aerobics", "venue": "Aquatic Center"},
        {"title": "Yoga", "venue": "Rec Center"},
    ]
    grouped = _group_series_by_venue(ongoing)
    assert [g["venue"] for g in grouped] == ["Aquatic Center", "Rec Center"]
    assert len(grouped[0]["cards"]) == 2
    assert len(grouped[1]["cards"]) == 1


# --- Tonight selector (DL-16) ----------------------------------------------


def _fixed_now() -> datetime:
    # 2099-03-10 17:00 local — far from seeded rows.
    return datetime(2099, 3, 10, 17, 0, tzinfo=_LHC)


def test_tonight_skips_already_started_morning_event() -> None:
    eids: list[str] = []
    day = _fixed_now().date()
    with SessionLocal() as db:
        # A 5 AM event already in the past at 5 PM must never be picked.
        _id, eid = _add_event(db, title="ZZ Dawn Swim", on=day, start=time(5, 0), loc="Pool")
        eids.append(eid)
        _id, eid = _add_event(db, title="ZZ Evening Jazz", on=day, start=time(19, 0), loc="Bridge")
        eids.append(eid)
        db.commit()
    try:
        with SessionLocal() as db:
            card = _tonight_card(db, now=_fixed_now())
        assert card is not None
        assert card["title"] == "ZZ Evening Jazz"
        assert card["k"] == "Tonight"  # evening label
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


def test_tonight_falls_through_to_tomorrow_label() -> None:
    eids: list[str] = []
    now = _fixed_now()
    tomorrow = now.date() + timedelta(days=1)
    with SessionLocal() as db:
        # Only a morning (past) event today; the next real event is tomorrow.
        _id, eid = _add_event(db, title="ZZ Past Only", on=now.date(), start=time(6, 0), loc="Pool")
        eids.append(eid)
        _id, eid = _add_event(db, title="ZZ Fair", on=tomorrow, start=time(10, 0), loc="Park")
        eids.append(eid)
        db.commit()
    try:
        with SessionLocal() as db:
            card = _tonight_card(db, now=now)
        assert card is not None
        assert card["title"] == "ZZ Fair"
        assert card["k"] == "Tomorrow"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


def test_tonight_prefers_oneoff_over_recurring_at_same_time() -> None:
    eids: list[str] = []
    now = _fixed_now()
    day = now.date()
    with SessionLocal() as db:
        _id, eid = _add_event(
            db, title="ZZ Class", on=day, start=time(19, 0), loc="Gym", recurring=True
        )
        eids.append(eid)
        _id, eid = _add_event(
            db, title="ZZ Concert", on=day, start=time(19, 0), loc="Bridge", recurring=False
        )
        eids.append(eid)
        db.commit()
    try:
        with SessionLocal() as db:
            card = _tonight_card(db, now=now)
        assert card is not None
        assert card["title"] == "ZZ Concert"  # one-off wins the tie
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


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
        assert cell["count"] == 4
        # The special one-off must be among the two visible pills.
        visible_titles = [e["title"] for e in cell["events"]]
        assert "ZZ Big Festival" in visible_titles
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


# --- /events-ui rendering + ?when= / ?date= ---------------------------------


def test_events_ui_renders_when_chips_and_sections() -> None:
    with TestClient(app) as client:
        body = client.get("/events-ui").text
    # Chip strip present with labeled filters.
    assert "ev-when-chips" in body
    assert "This Weekend" in body
    # Honest per-section total copy.
    assert "total" in body
    # Plain bucket labels preserved (E-1).
    assert "Today" in body and "This Week" in body and "Next Week" in body


def test_events_ui_when_filter_narrows_to_single_bucket() -> None:
    with TestClient(app) as client:
        body = client.get("/events-ui?when=today").text
    # Narrowed view drops the This Week / Next Week sections.
    assert 'aria-label="This Week"' not in body
    assert 'aria-label="Next Week"' not in body


def test_events_ui_date_deeplink_shows_single_day() -> None:
    with TestClient(app) as client:
        body = client.get("/events-ui?date=2099-04-12").text
    assert "Showing events for" in body
    assert "Back to all events" in body


def test_event_detail_uses_fraunces_font_stack() -> None:
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
        # DL-15: Fraunces/Figtree, not the old Georgia/lake_light stack.
        assert "Fraunces" in body and "Figtree" in body
        assert "lake_light.css" not in body
        assert "sandstone_events.css" in body
        # pre-line description container is present.
        assert "ev-detail-desc" in body
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
        # timed event with end renders DTSTART + DTEND
        assert "DTEND:" in body
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()
