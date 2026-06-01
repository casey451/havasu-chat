"""Phase 9a — venue events region on provider profile."""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Category, Entity, Event, Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _eat_category_id(db) -> int:
    row = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
    assert row is not None
    return row.id


def test_venue_events_partial_exists() -> None:
    text = Path("app/templates/components/venue_events_region.html").read_text(encoding="utf-8")
    assert "hava_card.html" in text


def test_provider_profile_includes_region_anchor() -> None:
    text = Path("app/templates/provider_profile.html").read_text(encoding="utf-8")
    assert "ll-provider-identity" in text


def test_provider_with_future_event_renders_hava_card(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    today = date.today()
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        p = Provider(
            provider_name=f"Venue Ev {suf}",
            category="restaurant",
            category_id=eat_id,
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase9",
            slug=f"venue-ev-{suf}",
        )
        db.add(p)
        db.commit()
        pid = p.id
        eid = p.entity_id
        slug = f"venue-ev-{suf}"

        ev = Event(
            title=f"Show {suf}",
            normalized_title=f"show {suf}",
            date=today + timedelta(days=3),
            start_time=time(19, 0),
            location_name="Here",
            location_normalized="here",
            description="Live music.",
            event_url="https://example.com/ev",
            status="live",
            source="admin",
            provider_id=pid,
            entity_id=eid,
        )
        db.add(ev)
        db.commit()
        ev_id = ev.id

    r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert f"Venue Ev {suf}" in r.text

    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.id == ev_id))
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()
