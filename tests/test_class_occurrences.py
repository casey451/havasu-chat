"""Venue class Schedules surface on the calendar + events feed (read-time bridge)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Event, Provider, Schedule
from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
)
from app.home import sandstone
from app.main import app


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_venue_with_class(title: str, days: list[str]) -> tuple[str, str, str]:
    """Provider (+entity) with one recurring class. Returns (slug, entity_id, name)."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Calendar Combat {suf}", category="fitness_sports",
            verified=True, draft=False, is_active=True, pending_review=False,
            source="test-class-occurrences",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        db.add(
            Schedule(
                entity_id=eid, schedule_type="recurring", days_of_week=days,
                start_time=time(18, 0), end_time=time(19, 0), notes=title,
                created_at=_now(), updated_at=_now(),
            )
        )
        db.commit()
        return p.slug, eid, p.provider_name


def test_expansion_hits_every_matching_weekday() -> None:
    title = f"BJJ Fundamentals {uuid.uuid4().hex[:6]}"
    slug, _eid, name = _make_venue_with_class(title, ["monday", "tuesday", "wednesday", "thursday"])
    with SessionLocal() as db:
        occs = [
            o for o in class_occurrences_in_window(
                db, window_start=date(2026, 12, 1), window_end=date(2026, 12, 31)
            )
            if o.title == title
        ]
    # December 2026: Mon-Thu occur 4-5 times each; 4 weekdays -> 19 occurrences.
    assert len(occs) == 19
    assert {o.date.weekday() for o in occs} == {0, 1, 2, 3}
    assert all(o.provider_slug == slug for o in occs)
    assert occs[0].url == f"/provider/{slug}"


def test_event_duplicates_dropped_by_title_and_date() -> None:
    title = f"Lap Swim Clone {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["friday"])
    with SessionLocal() as db:
        occs = [
            o for o in class_occurrences_in_window(
                db, window_start=date(2026, 12, 4), window_end=date(2026, 12, 11)
            )
            if o.title == title
        ]
    assert len(occs) == 2  # Fri Dec 4 + Fri Dec 11
    kept = drop_event_duplicates(occs, {(title.lower(), date(2026, 12, 4))})
    assert [o.date for o in kept] == [date(2026, 12, 11)]


def test_month_calendar_shows_schedule_classes() -> None:
    title = f"Calendar Karate {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["tuesday"])
    with SessionLocal() as db:
        cal = sandstone.calendar_month(db, year=2026, month=12, today=date(2026, 12, 1))
    cells = [c for week in cal["weeks"] for c in week]
    tuesdays = [
        c for c in cells
        if c.get("in_month") and date.fromisoformat(c["iso"]).weekday() == 1
    ]
    assert tuesdays, "December 2026 has Tuesdays"
    for cell in tuesdays:
        titles = {e["title"] for e in cell["events"]}
        assert title in titles or cell["overflow"] > 0 or cell["count"] >= 1


def test_events_ui_day_page_lists_class_with_venue_link() -> None:
    title = f"Day Page Judo {uuid.uuid4().hex[:6]}"
    slug, _eid, _name = _make_venue_with_class(title, ["wednesday"])
    client = TestClient(app)
    r = client.get("/events-ui?date=2026-12-09")  # a Wednesday
    assert r.status_code == 200
    assert title in r.text
    assert f"/provider/{slug}" in r.text


def test_events_ui_skips_class_that_is_also_an_event() -> None:
    """Aquatic-style duplicates (class exists as a recurring Event too) show once."""
    title = f"Dup Aqua Fit {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["thursday"])
    with SessionLocal() as db:
        db.add(
            Event(
                title=title, normalized_title=title.lower(),
                date=date(2026, 12, 10), start_time=time(18, 0),
                location_name="Aquatic Center", location_normalized="aquatic center",
                description="The event-table twin of the schedule row.",
                source="parks_rec", tags=["class"], status="live",
            )
        )
        db.commit()
    client = TestClient(app)
    r = client.get("/events-ui?date=2026-12-10")  # a Thursday
    assert r.status_code == 200
    assert r.text.count(title) == 1


def test_class_cards_survive_busy_day_cap() -> None:
    """The per-window cap must not silently drop class series on busy days
    (prod: 12+ one-off events filled the 16-card cap before any class)."""
    title = f"Cap Survivor Aikido {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["saturday"])
    with SessionLocal() as db:
        for i in range(20):
            db.add(
                Event(
                    title=f"Busy Day Filler {i} {uuid.uuid4().hex[:4]}",
                    normalized_title=f"busy day filler {i}",
                    date=date(2026, 12, 12), start_time=time(10, 0),
                    location_name="Main St", location_normalized="main st",
                    description="One-off filler event to saturate the window cap.",
                    source="admin", tags=["community"], status="live",
                )
            )
        db.commit()
    client = TestClient(app)
    r = client.get("/events-ui?date=2026-12-12")  # a Saturday
    assert r.status_code == 200
    assert title in r.text
