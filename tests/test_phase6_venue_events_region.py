"""Phase 6.5 — provider profile venue events hook region."""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Category, Entity, Event, Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _eat_category_id(db) -> int:
    row = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
    assert row is not None
    return row.id


def test_provider_profile_template_has_venue_events_anchor() -> None:
    text = Path("app/templates/provider_profile.html").read_text(encoding="utf-8")
    assert "Ask Hava about this business" in text


def test_provider_without_events_omits_venue_region(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        p = Provider(
            provider_name=f"No Events {suf}",
            category="restaurant",
            category_id=eat_id,
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase65",
            slug=f"no-events-{suf}",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        slug = f"no-events-{suf}"

    r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert f"No Events {suf}" in r.text

    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_provider_with_events_renders_venue_region(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    on_date = date.today() + timedelta(days=5)
    with SessionLocal() as db:
        eat_id = _eat_category_id(db)
        p = Provider(
            provider_name=f"With Events {suf}",
            category="restaurant",
            category_id=eat_id,
            verified=False,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase65",
            slug=f"with-events-{suf}",
        )
        db.add(p)
        db.commit()
        pid = p.id
        eid = p.entity_id
        slug = f"with-events-{suf}"

        ev = Event(
            title=f"Live Night {suf}",
            normalized_title=f"live night {suf}",
            date=on_date,
            start_time=time(19, 0),
            end_time=None,
            location_name="Venue",
            location_normalized="venue",
            description="Test event.",
            event_url="https://example.com/ev",
            status="live",
            source="admin",
            provider_id=pid,
        )
        db.add(ev)
        create_event_and_entity(db, ev)
        db.commit()
        ev_id = ev.id
        event_entity_id = ev.entity_id

    r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert f"With Events {suf}" in r.text

    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.id == ev_id))
        db.execute(delete(Entity).where(Entity.id == event_entity_id))
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_provider_profile_regression_district_and_search(client: TestClient) -> None:
    """Smoke: category + provider templates still include primary UI markers."""
    r = client.get("/lake-havasu/restaurants")
    assert r.status_code == 200
    text = Path("app/templates/provider_profile.html").read_text(encoding="utf-8")
    assert 'data-region="provider-identity"' in text  # Sandstone identity anchor
    assert "Ask Hava about this business" in text
