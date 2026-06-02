"""Regression: /category/events collapses recurring series (P0 Task 4 follow-up).

The page dedup keyed on event.id, but a daily class is many distinct rows, so it
flooded the grid. It now dedups on the series key (next occurrence per series).
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

from sqlalchemy import delete

from app.api.routes.category_pages import _build_events_category_stream
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Category, EntityCategory, Event


def _events_category_id(db) -> int:
    row = db.query(Category).filter(Category.slug == "events").first()
    assert row is not None
    return row.id


def _make_event(db, *, title: str, on_date: date, start: time, loc: str) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name=loc,
        location_normalized=loc.lower(),
        description="Test",
        event_url="https://example.com/e",
        status="live",
        source="test-events-collapse",
        is_recurring=False,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    db.add(EntityCategory(entity_id=ev.entity_id, category_id=_events_category_id(db), is_primary=True))
    db.flush()
    return ev.entity_id


def test_events_category_page_collapses_recurring_series() -> None:
    suffix = uuid.uuid4().hex[:6]
    series_title = f"ZZ Lap Swim {suffix}"
    oneoff_title = f"ZZ Gala {suffix}"
    ids: list[str] = []
    start = now_lake_havasu()
    monday = start.date() - timedelta(days=start.weekday())
    with SessionLocal() as db:
        for d in range(5):  # Mon-Fri, same series
            ids.append(
                _make_event(
                    db,
                    title=series_title,
                    on_date=monday + timedelta(days=d),
                    start=time(5, 0),
                    loc="Aquatic Center",
                )
            )
        ids.append(
            _make_event(
                db, title=oneoff_title, on_date=monday, start=time(18, 0), loc="London Bridge"
            )
        )
        db.commit()
    try:
        with SessionLocal() as db:
            stream = _build_events_category_stream(
                db,
                when=None,
                sort_key="chronological",
                ref_lat=34.48,
                ref_lng=-114.32,
                now=now_lake_havasu(),
                limit=80,
            )

        def _title(vm) -> str:
            return getattr(vm, "name", None) or ""

        titles = [_title(vm) for vm in stream]
        assert titles.count(series_title) == 1, "recurring series should appear once"
        assert titles.count(oneoff_title) == 1
    finally:
        with SessionLocal() as db:
            from app.db.models import Entity

            db.execute(delete(EntityCategory).where(EntityCategory.entity_id.in_(ids)))
            db.execute(delete(Event).where(Event.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()
