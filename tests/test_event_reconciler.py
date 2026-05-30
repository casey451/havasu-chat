"""Central cross-source event reconciler (composes Phase 9b dedup)."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.contrib.event_reconciler import (
    EVENT_SOURCE_PRIORITY,
    combine_sources,
    reconcile_event,
)
from app.db.contribution_store import normalize_submission_url
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Event
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
    location_name: str = "Venue",
    source: str = "river_scene",
    source_url: str | None = None,
    description: str = "",
    operator_override: bool = False,
) -> Event:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name=location_name,
        location_normalized=location_name.lower(),
        description=description,
        event_url="https://example.com/existing",
        source_url=source_url,
        status="live",
        source=source,
        operator_override=operator_override,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    db.flush()
    return ev


def _payload(
    *,
    name: str,
    start_date: date,
    start_time: time,
    venue_name: str | None = None,
    source: str = "go_lake_havasu",
    source_stable_url: str | None = None,
    event_url: str = "https://www.golakehavasu.com/events/x/",
    description: str = "A description that is long enough to be useful.",
) -> EventPayload:
    return EventPayload(
        name=name,
        entity_type="event",
        source=source,
        start_date=start_date,
        start_time=start_time,
        venue_name=venue_name,
        event_url=event_url,
        source_stable_url=source_stable_url,
        description=description,
        tags=["events"],
    )


def test_priority_ordering() -> None:
    assert EVENT_SOURCE_PRIORITY["operator"] < EVENT_SOURCE_PRIORITY["go_lake_havasu"]
    assert EVENT_SOURCE_PRIORITY["go_lake_havasu"] < EVENT_SOURCE_PRIORITY["city"]
    assert EVENT_SOURCE_PRIORITY["city"] < EVENT_SOURCE_PRIORITY["river_scene"]


def test_combine_sources_orders_by_priority_and_dedupes() -> None:
    assert combine_sources("river_scene", "go_lake_havasu") == "go_lake_havasu,river_scene"
    assert combine_sources("go_lake_havasu,river_scene", "go_lake_havasu") == (
        "go_lake_havasu,river_scene"
    )


def test_empty_db_inserts(db) -> None:
    p = _payload(name="Brand New Event", start_date=date(2031, 4, 4), start_time=time(10, 0))
    r = reconcile_event(db, p)
    assert r.action == "insert"


def test_source_url_exact_is_update(db) -> None:
    src = normalize_submission_url("https://www.golakehavasu.com/events/reimport/")
    _event(
        db,
        title="Reimport Me",
        on_date=date(2031, 5, 5),
        start=time(9, 0),
        source="go_lake_havasu",
        source_url=src,
    )
    p = _payload(
        name="Reimport Me",
        start_date=date(2031, 5, 5),
        start_time=time(9, 0),
        source_stable_url="https://www.golakehavasu.com/events/reimport/",
    )
    r = reconcile_event(db, p)
    assert r.action == "update"
    assert r.reason == "source_url exact match"


def test_cross_source_duplicate_merges_with_priority(db) -> None:
    # A river_scene farmers market already exists; the golakehavasu (higher
    # priority) re-discovery of the same event on the same day must merge,
    # not double-book.
    d = date(2031, 6, 6)
    existing = _event(
        db,
        title="Lake Havasu Farmers Market",
        on_date=d,
        start=time(8, 0),
        source="river_scene",
        description="",
    )
    p = _payload(
        name="Lake Havasu Farmers Market",
        start_date=d,
        start_time=time(8, 0),
        venue_name="The KAWS",
        source="go_lake_havasu",
        description="CVB blurb about the market.",
    )
    r = reconcile_event(db, p)
    assert r.action == "duplicate"
    assert r.existing_id == existing.id
    assert r.combined_source == "go_lake_havasu,river_scene"
    # Higher-priority source fills the empty description.
    assert r.merge_fields is not None
    assert r.merge_fields.get("description") == "CVB blurb about the market."
    assert r.merge_fields.get("source") == "go_lake_havasu,river_scene"


def test_same_date_same_venue_loose_title_is_ambiguous(db) -> None:
    d = date(2031, 7, 7)
    existing = _event(
        db,
        title="Downtown Block Party",
        on_date=d,
        start=time(18, 0),
        location_name="Main Stage",
        source="river_scene",
    )
    p = _payload(
        name="Downtown Street Party",  # token_sort_ratio ~68 vs existing
        start_date=d,
        start_time=time(18, 0),
        venue_name="Main Stage",
    )
    r = reconcile_event(db, p)
    assert r.action == "ambiguous"
    assert r.existing_id == existing.id


def test_distinct_event_same_day_different_venue_inserts(db) -> None:
    d = date(2031, 8, 8)
    _event(
        db,
        title="Morning Yoga",
        on_date=d,
        start=time(7, 0),
        location_name="Beach",
        source="river_scene",
    )
    p = _payload(
        name="Evening Lecture Series",
        start_date=d,
        start_time=time(19, 0),
        venue_name="Library",
    )
    r = reconcile_event(db, p)
    assert r.action == "insert"


def test_operator_override_only_appends_provenance(db) -> None:
    d = date(2031, 9, 9)
    _event(
        db,
        title="Operator Fixed Title",
        on_date=d,
        start=time(12, 0),
        source="operator",
        description="Hand curated.",
        operator_override=True,
    )
    p = _payload(
        name="Operator Fixed Title",
        start_date=d,
        start_time=time(12, 0),
        description="Scraper would overwrite but must not.",
    )
    r = reconcile_event(db, p)
    assert r.action == "duplicate"
    assert r.merge_fields == {"source": r.combined_source}
