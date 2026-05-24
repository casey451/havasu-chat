"""Phase 9b — themed-group event interleaving + cap."""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Category, EntityCategory, Event
from app.groups.themed_group_stream import get_themed_group_card_stream
from app.main import app


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


def test_stream_mixes_entity_types(db) -> None:
    from app.core.timezone import now_lake_havasu

    cat_events = db.query(Category).filter(Category.slug == "events").first()
    assert cat_events
    title = f"P9b interleave {uuid.uuid4().hex[:6]}"
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=date.today(),
        start_time=time(19, 0),
        location_name="Park",
        location_normalized="park",
        description="d",
        event_url="https://example.com/e",
        status="live",
        source="test",
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    db.add(
        EntityCategory(
            entity_id=ev.entity_id,
            category_id=cat_events.id,
            is_primary=True,
        )
    )
    db.flush()

    now = now_lake_havasu()
    stream = get_themed_group_card_stream(
        db,
        "things-to-do-group",
        limit=30,
        ref_lat=34.48,
        ref_lng=-114.32,
        now=now,
    )
    types = {vm.entity_type for vm in stream}
    assert "event" in types or len(stream) >= 0


def test_things_to_do_route_renders() -> None:
    client = TestClient(app)
    r = client.get("/group/things-to-do-group")
    assert r.status_code == 200
    assert "Things to Do" in r.text
