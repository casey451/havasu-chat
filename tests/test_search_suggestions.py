"""``GET /api/search/suggestions`` — lightweight autocomplete endpoint."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Provider
from app.main import app


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _entity(*, name: str, slug: str | None = None) -> Entity:
    s = slug or f"ent-{uuid.uuid4().hex[:12]}"
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=s,
        name=name,
        description=f"{name} description",
        source="test-search-suggestions",
    )


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_suggestions_short_query_returns_empty() -> None:
    with TestClient(app) as client:
        r = client.get("/api/search/suggestions", params={"q": "a"})
    assert r.status_code == 200
    assert r.json() == []


def test_suggestions_missing_query_returns_empty() -> None:
    with TestClient(app) as client:
        r = client.get("/api/search/suggestions")
    assert r.status_code == 200
    assert r.json() == []


def test_suggestions_match_by_name_and_shape(db: Session) -> None:
    suf = _suffix()
    mark = f"Zephyr {suf}"
    ent = _entity(name=f"{mark} Boat Rentals", slug=f"zephyr-{suf}")
    p = Provider(
        provider_name=ent.name,
        slug=f"zephyr-{suf}",
        category="recreation",
        google_primary_category="boat_rental_service",
        source="test-search-suggestions",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/api/search/suggestions", params={"q": "Zephyr"})
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) <= 8
    hit = next(x for x in rows if x["name"].startswith(mark))
    assert hit["type"] == ENTITY_TYPE_COMMERCIAL
    assert hit["subcategory"] == "boat_rental_service"
    assert hit["url"] == f"/provider/zephyr-{suf}"


def test_suggestions_substring_match(db: Session) -> None:
    suf = _suffix()
    mark = f"Sunset {suf}"
    ent = _entity(name=f"The {mark} Grill", slug=f"sunset-{suf}")
    p = Provider(
        provider_name=ent.name,
        slug=f"sunset-{suf}",
        category="food_drink",
        source="test-search-suggestions",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/api/search/suggestions", params={"q": mark})
    assert r.status_code == 200
    names = [x["name"] for x in r.json()]
    assert any(mark in n for n in names), names


def test_suggestions_excludes_inactive(db: Session) -> None:
    suf = _suffix()
    mark = f"Hidden {suf}"
    ent = _entity(name=f"{mark} Closed Shop", slug=f"hidden-{suf}")
    ent.is_active = False
    db.add(ent)
    db.commit()

    with TestClient(app) as client:
        r = client.get("/api/search/suggestions", params={"q": mark})
    assert r.status_code == 200
    names = [x["name"] for x in r.json()]
    assert all(mark not in n for n in names), names
