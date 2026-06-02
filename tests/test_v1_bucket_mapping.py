"""Regression: /api/v1 bucket mapping + subcategory filter (P0 follow-up).

The legacy->bucket map used to key on spec-style slugs that never matched the
stored ``Provider.category`` values, so the whole /api/v1 surface miscounted and
the ``?category=`` filter returned nothing for Recreation/Sports/Shopping/Stay.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.main import app
from app.v1.categories import bucket_for_legacy_category


@pytest.mark.parametrize(
    "legacy,bucket",
    [
        ("lake_recreation", "recreation-outdoors"),
        ("boat_rental", "recreation-outdoors"),
        ("retail", "shopping"),
        ("lodging", "stay"),
        ("fitness_sports", "sports-fitness"),
        ("beauty_personal_care", "services"),
        ("professional_services", "services"),
        ("restaurant", "food-drink"),
        ("entertainment_attractions", "events"),
    ],
)
def test_bucket_for_legacy_category_uses_real_values(legacy: str, bucket: str) -> None:
    assert bucket_for_legacy_category(legacy) == bucket


def _seed(db, *, name: str, category: str, subcategory: str | None) -> str:
    p = Provider(
        provider_name=name,
        category=category,
        subcategory=subcategory,
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-v1-bucket",
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
    )
    db.add(p)
    db.commit()
    return p.entity_id


def test_api_businesses_category_filter_returns_bucket_members() -> None:
    ids: list[str] = []
    name = f"ZZ Marina {uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        ids.append(_seed(db, name=name, category="lake_recreation", subcategory="on-the-water"))
    try:
        client = TestClient(app)
        r = client.get("/api/businesses?category=recreation-outdoors&limit=100")
        assert r.status_code == 200
        names = [i["name"] for i in r.json()["items"]]
        assert name in names  # previously this filter returned nothing
        # And it does NOT leak into Services any more.
        r2 = client.get("/api/businesses?category=services&limit=100")
        assert name not in [i["name"] for i in r2.json()["items"]]
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()


def test_api_businesses_subcategory_filter_uses_column() -> None:
    ids: list[str] = []
    name = f"ZZ Storage Co {uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        ids.append(_seed(db, name=name, category="services", subcategory="storage"))
    try:
        client = TestClient(app)
        r = client.get("/api/businesses?subcategory=storage&limit=100")
        assert r.status_code == 200
        items = {i["name"]: i for i in r.json()["items"]}
        assert name in items
        assert items[name]["subcategory"] == "storage"  # serializer exposes the column
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()
