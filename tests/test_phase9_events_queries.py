"""Phase 9a — events_in_window query helpers."""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Category, EntityCategory, Event
from app.events.queries import event_window_for_chip, events_in_window


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


def _events_category_id(db) -> int:
    row = db.query(Category).filter(Category.slug == "events").first()
    assert row is not None
    return row.id


def _make_live_event(db, *, on_date: date, rrule: str | None = None) -> Event:
    title = f"P9 {uuid.uuid4().hex[:6]}"
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=time(19, 0),
        location_name="Venue",
        location_normalized="venue",
        description="Test",
        event_url="https://example.com/e",
        status="live",
        source="test_phase9",
        is_recurring=bool(rrule),
        rrule=rrule,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    cat_id = _events_category_id(db)
    db.add(
        EntityCategory(
            entity_id=ev.entity_id,
            category_id=cat_id,
            is_primary=True,
        )
    )
    db.flush()
    return ev


def test_event_window_for_chip_today() -> None:
    today = date(2026, 5, 23)
    assert event_window_for_chip("today", today=today) == (today, today)


def test_event_window_for_chip_this_weekend_friday_before() -> None:
    today = date(2026, 5, 21)
    start, end = event_window_for_chip("this-weekend", today=today)
    assert start.weekday() == 4
    assert end.weekday() == 6


def test_events_in_window_non_recurring(db) -> None:
    ev = _make_live_event(db, on_date=date(2026, 8, 1))
    db.commit()
    try:
        flat = events_in_window(
            db,
            window_start=date(2026, 8, 1),
            window_end=date(2026, 8, 31),
            category_slug="events",
        )
        ids = {e.id for e, _ in flat}
        assert ev.id in ids
    finally:
        db.execute(delete(Event).where(Event.id == ev.id))
        db.execute(delete(EntityCategory).where(EntityCategory.entity_id == ev.entity_id))
        db.commit()


def test_events_in_window_recurring(db) -> None:
    ev = _make_live_event(
        db,
        on_date=date(2026, 6, 3),
        rrule="FREQ=WEEKLY;BYDAY=TU",
    )
    db.commit()
    try:
        flat = events_in_window(
            db,
            window_start=date(2026, 6, 1),
            window_end=date(2026, 6, 30),
            category_slug="events",
        )
        dates = [d for e, d in flat if e.id == ev.id]
        assert len(dates) >= 2
    finally:
        db.execute(delete(Event).where(Event.id == ev.id))
        db.execute(delete(EntityCategory).where(EntityCategory.entity_id == ev.entity_id))
        db.commit()
