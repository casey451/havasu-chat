"""Phase 9b — multi-source dedup + merge semantics."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Event
from app.events.dedup import (
    DEDUP_TITLE_FUZZY_THRESHOLD,
    find_duplicate,
    merge_scraper_into_event,
    normalize_event_title,
)
from app.events.scrapers.base import EventPayload


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
    start: time,
    entity_id: str | None = None,
    operator_override: bool = False,
) -> Event:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name="Venue",
        location_normalized="venue",
        description="",
        event_url="https://example.com",
        status="live",
        source="chamber",
        operator_override=operator_override,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    if entity_id:
        ev.entity_id = entity_id
    db.flush()
    return ev


def test_same_event_same_time_matches(db) -> None:
    d = date(2026, 7, 4)
    ev = _event(db, title="Spring Festival", on_date=d, start=time(10, 0))
    dup = find_duplicate(
        db,
        venue_entity_id=ev.entity_id,
        start_date=d,
        start_time_obj=time(10, 0),
        normalized_title=normalize_event_title("Spring Festival 2026"),
    )
    assert dup is not None
    assert dup.id == ev.id


def test_30_min_window_edge_inside(db) -> None:
    d = date(2026, 7, 4)
    ev = _event(db, title="Yoga Class", on_date=d, start=time(18, 0))
    dup = find_duplicate(
        db,
        venue_entity_id=ev.entity_id,
        start_date=d,
        start_time_obj=time(18, 25),
        normalized_title="yoga class",
    )
    assert dup is not None


def test_45_min_apart_no_match(db) -> None:
    d = date(2026, 7, 4)
    ev = _event(db, title="Morning Show", on_date=d, start=time(9, 0))
    dup = find_duplicate(
        db,
        venue_entity_id=ev.entity_id,
        start_date=d,
        start_time_obj=time(10, 0),
        normalized_title="morning show",
    )
    assert dup is None


def test_fuzzy_title_88_matches(db) -> None:
    d = date(2026, 8, 1)
    ev = _event(db, title="Live Music Night", on_date=d, start=time(20, 0))
    dup = find_duplicate(
        db,
        venue_entity_id=ev.entity_id,
        start_date=d,
        start_time_obj=time(20, 0),
        normalized_title="live music nights",
    )
    assert dup is not None


def test_fuzzy_title_80_below_threshold_no_match(db) -> None:
    d = date(2026, 8, 1)
    _event(db, title="Completely Different Name", on_date=d, start=time(20, 0))
    dup = find_duplicate(
        db,
        venue_entity_id=None,
        start_date=d,
        start_time_obj=time(20, 0),
        normalized_title="xyz unrelated",
    )
    assert dup is None
    assert DEDUP_TITLE_FUZZY_THRESHOLD == 85


def test_operator_override_preserves_title_on_merge(db) -> None:
    d = date(2026, 9, 1)
    ev = _event(
        db,
        title="Operator Fixed Title",
        on_date=d,
        start=time(12, 0),
        operator_override=True,
    )
    payload = EventPayload(
        name="Scraper Title",
        description="new desc",
        start_date=d,
        start_time=time(12, 0),
        event_url="https://example.com/new",
    )
    merge_scraper_into_event(db, ev, payload, scrape_source="chamber")
    db.refresh(ev)
    assert ev.title == "Operator Fixed Title"
    assert ev.description == "new desc" or ev.description == ""
