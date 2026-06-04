"""WP-4: DB-backed canonical-URL + recurring-series dedup primitives."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Event
from app.events.dedup import (
    find_duplicate_by_canonical_url,
    find_recurring_series_instance,
)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


def _event(
    db,
    *,
    title: str,
    on_date: date,
    start: time = time(10, 0),
    location_name: str = "Venue",
    event_url: str = "https://example.com",
    source_url: str | None = None,
    source: str = "go_lake_havasu",
) -> Event:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name=location_name,
        location_normalized=location_name.lower(),
        description="",
        event_url=event_url,
        source_url=source_url,
        status="live",
        source=source,
        operator_override=False,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    db.flush()
    return ev


def test_canonical_url_match_across_sources(db) -> None:
    existing = _event(
        db,
        title="Jazz Night",
        on_date=date(2026, 7, 1),
        event_url="https://www.facebook.com/events/4242/",
        source="go_lake_havasu",
    )
    # A river_scene re-import of the same FB event id (with tracking noise).
    dup = find_duplicate_by_canonical_url(
        db,
        candidate_urls=["https://facebook.com/events/4242?fbclid=ABC", None],
    )
    assert dup is not None
    assert dup.id == existing.id


def test_canonical_url_no_match(db) -> None:
    _event(
        db,
        title="Jazz Night",
        on_date=date(2026, 7, 1),
        event_url="https://example.com/events/jazz",
    )
    assert find_duplicate_by_canonical_url(db, candidate_urls=["https://example.com/events/blues"]) is None


def test_recurring_series_instance_same_day(db) -> None:
    d = date(2026, 7, 4)  # a Saturday
    existing = _event(
        db,
        title="Farmers Market",
        on_date=d,
        location_name="Visitor Center",
    )
    dup = find_recurring_series_instance(
        db,
        venue_name="Visitor Center",
        title="Farmers Market!",  # punctuation normalized away
        start_date=d,
    )
    assert dup is not None
    assert dup.id == existing.id


def test_recurring_series_instance_other_day_no_match(db) -> None:
    _event(
        db,
        title="Farmers Market",
        on_date=date(2026, 7, 4),
        location_name="Visitor Center",
    )
    dup = find_recurring_series_instance(
        db,
        venue_name="Visitor Center",
        title="Farmers Market",
        start_date=date(2026, 7, 11),  # next Saturday -- distinct occurrence
    )
    assert dup is None
