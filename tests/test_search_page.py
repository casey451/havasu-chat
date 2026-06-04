"""WP-11 — ``GET /search`` keyword results page (DL-6 phase 2)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_EVENT
from app.db.models import Entity, Event, Provider
from app.main import app


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _commercial_entity(*, name: str, slug: str) -> Entity:
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=slug,
        name=name,
        description=f"{name} description",
        source="test-search-page",
    )


def _event_entity(*, name: str) -> Entity:
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_EVENT,
        slug=f"ev-{uuid.uuid4().hex[:12]}",
        name=name,
        description=name,
        source="test-search-page",
    )


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_search_page_returns_200_with_provider_row(db: Session) -> None:
    suf = _suffix()
    mark = f"PipeFix {suf}"
    slug = f"pipefix-{suf}"
    ent = _commercial_entity(name=f"{mark} Plumbing Services", slug=slug)
    p = Provider(
        provider_name=ent.name,
        slug=slug,
        category="home_services",
        google_primary_category="plumber",
        phone="928-555-0142",
        address="123 Main St",
        source="test-search-page",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": "plumber"})
    assert r.status_code == 200
    body = r.text
    # Provider row exposes name, link, and phone.
    assert mark in body
    assert f"/provider/{slug}" in body
    assert "928-555-0142" in body


def test_search_page_event_row_links_to_permalink(db: Session) -> None:
    suf = _suffix()
    mark = f"LanternFest{suf}"
    ent = _event_entity(name=mark)
    ev = Event(
        id=str(uuid.uuid4()),
        title=f"{mark} on the Channel",
        normalized_title=mark.lower(),
        date=dt.date(2030, 7, 4),
        start_time=dt.time(18, 0),
        location_name="London Bridge",
        location_normalized="london bridge",
        description="A lantern festival.",
        status="live",
        source="test-search-page",
        entity_id=ent.id,
    )
    db.add_all([ent, ev])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": mark})
    assert r.status_code == 200
    body = r.text
    assert mark in body
    assert f"/events/{ev.id}" in body
    assert "London Bridge" in body


def test_search_page_blank_q_shows_empty_state() -> None:
    with TestClient(app) as client:
        r = client.get("/search", params={"q": "   "})
    assert r.status_code == 200
    # Empty state references Ask Hava and does not render result sections.
    assert "/chat" in r.text
    assert "Businesses" not in r.text


def test_search_page_no_matches_shows_empty_state() -> None:
    with TestClient(app) as client:
        r = client.get("/search", params={"q": f"zzqqxx{_suffix()}nomatch"})
    assert r.status_code == 200
    body = r.text
    assert "No matches for" in body
    assert "/chat?q=" in body


def test_search_page_does_not_leak_internal_fields(db: Session) -> None:
    suf = _suffix()
    slug = f"leakcheck-{suf}"
    ent = _commercial_entity(name=f"LeakCheck {suf} Cafe", slug=slug)
    p = Provider(
        provider_name=ent.name,
        slug=slug,
        category="food_drink",
        google_primary_category="cafe",
        phone="928-555-0199",
        source="test-search-page",
        draft=False,
        is_active=True,
        entity_id=ent.id,
        embedding=[0.1, 0.2, 0.3],
        raw_enrichment_json={"secret": "do-not-leak"},
        attributes={"hero_pin_photo_url": "https://example.com/h.jpg"},
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": "cafe"})
    assert r.status_code == 200
    body = r.text
    assert "LeakCheck" in body
    assert "do-not-leak" not in body
    assert "raw_enrichment_json" not in body
    assert ent.id not in body  # internal entity id not exposed


def test_search_page_excludes_draft_and_inactive(db: Session) -> None:
    suf = _suffix()
    mark = f"DraftDojo{suf}"
    ent = _commercial_entity(name=f"{mark} Karate", slug=f"draftdojo-{suf}")
    p = Provider(
        provider_name=ent.name,
        slug=f"draftdojo-{suf}",
        category="misc",
        source="test-search-page",
        draft=True,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": mark})
    assert r.status_code == 200
    # The query echoes in the <title>, but the draft provider's row/link must not render.
    assert f"/provider/draftdojo-{suf}" not in r.text
    assert "No matches for" in r.text


def test_header_search_form_action_points_to_search() -> None:
    with TestClient(app) as client:
        h = client.get("/home")
        assert h.status_code == 200
        assert 'class="header-search" action="/search"' in h.text
        # Ask Hava remains one click via the secondary CTA.
        assert "/chat?q=" in h.text
