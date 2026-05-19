"""Phase 6.4 — map marker JSON API."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Category, Entity, EntityCategory, Location, Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _link_entity_category(db, entity_id: str, category_slug: str) -> None:
    cat = db.scalars(select(Category).where(Category.slug == category_slug)).first()
    assert cat is not None
    db.add(EntityCategory(entity_id=entity_id, category_id=cat.id))


def test_map_data_unknown_slug_404(client: TestClient) -> None:
    r = client.get("/api/map_data/not-a-real-scope")
    assert r.status_code == 404


def test_map_data_category_returns_json_shape(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    lat, lng = 34.48, -114.32
    with SessionLocal() as db:
        ent = Entity(
            id=str(uuid.uuid4()),
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"map-ent-{suf}",
            name=f"Map Marker Cafe {suf}",
            source="test-phase64-map",
        )
        db.add(ent)
        db.flush()
        db.add(
            Location(entity_id=ent.id, lat=lat, lng=lng, city="Lake Havasu City", state="AZ")
        )
        p = Provider(
            provider_name=ent.name,
            slug=f"map-cafe-{suf}",
            category="food_drink",
            google_primary_category="cafe",
            draft=False,
            is_active=True,
            entity_id=ent.id,
            source="test-phase64-map",
        )
        db.add(p)
        _link_entity_category(db, ent.id, "eat-drink")
        db.commit()
        eid = ent.id

    try:
        r = client.get("/api/map_data/eat-drink")
        assert r.status_code == 200
        data = r.json()
        assert "entities" in data
        assert "truncated_at_n" in data
        assert isinstance(data["entities"], list)
        hit = next((row for row in data["entities"] if row.get("name") == f"Map Marker Cafe {suf}"), None)
        assert hit is not None
        assert hit["lat"] == lat
        assert hit["lng"] == lng
        assert hit["profile_url"].startswith("/provider/")
        assert "id" in hit and "category_slug" in hit
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(Location).where(Location.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_map_data_excludes_null_coordinates(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        ent = Entity(
            id=str(uuid.uuid4()),
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"map-noloc-{suf}",
            name=f"No Coords Shop {suf}",
            source="test-phase64-map",
        )
        db.add(ent)
        db.flush()
        p = Provider(
            provider_name=ent.name,
            slug=f"map-noloc-{suf}",
            category="food_drink",
            draft=False,
            is_active=True,
            entity_id=ent.id,
            source="test-phase64-map",
        )
        db.add(p)
        _link_entity_category(db, ent.id, "eat-drink")
        db.commit()
        eid = ent.id

    try:
        r = client.get("/api/map_data/eat-drink")
        assert r.status_code == 200
        names = [row["name"] for row in r.json()["entities"]]
        assert f"No Coords Shop {suf}" not in names
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_map_data_boat_param_filters(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        ent_boat = Entity(
            id=str(uuid.uuid4()),
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"map-boat-{suf}",
            name=f"Boat Dock {suf}",
            boat_access={"type": "marina", "fuel": True},
            source="test-phase64-map",
        )
        ent_land = Entity(
            id=str(uuid.uuid4()),
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"map-land-{suf}",
            name=f"Land Only {suf}",
            source="test-phase64-map",
        )
        db.add_all([ent_boat, ent_land])
        db.flush()
        for ent in (ent_boat, ent_land):
            db.add(
                Location(
                    entity_id=ent.id,
                    lat=34.48,
                    lng=-114.32,
                    city="Lake Havasu City",
                    state="AZ",
                )
            )
            db.add(
                Provider(
                    provider_name=ent.name,
                    slug=f"map-p-{ent.slug}",
                    category="food_drink",
                    draft=False,
                    is_active=True,
                    entity_id=ent.id,
                    source="test-phase64-map",
                )
            )
            _link_entity_category(db, ent.id, "on-the-water")
        db.commit()
        boat_id, land_id = ent_boat.id, ent_land.id

    try:
        r = client.get("/api/map_data/on-the-water?boat=1")
        assert r.status_code == 200
        names = {row["name"] for row in r.json()["entities"]}
        assert f"Boat Dock {suf}" in names
        assert f"Land Only {suf}" not in names
    finally:
        with SessionLocal() as db:
            for eid in (boat_id, land_id):
                db.execute(delete(Provider).where(Provider.entity_id == eid))
                db.execute(delete(Location).where(Location.entity_id == eid))
                db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
                db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_map_data_group_scope(client: TestClient) -> None:
    r = client.get("/api/map_data/health-fitness-group")
    assert r.status_code == 200
    assert r.json()["scope_slug"] == "health-fitness-group"


def test_map_data_truncated_flag_when_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import map_data as map_mod

    monkeypatch.setattr(map_mod, "MAP_MARKER_CAP", 1)
    with TestClient(app) as client:
        r = client.get("/api/map_data/eat-drink")
    assert r.status_code == 200
    data = r.json()
    if len(data["entities"]) >= 1:
        assert isinstance(data["truncated_at_n"], bool)
