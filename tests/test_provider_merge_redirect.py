"""P1.10 — merged-away provider slugs 301 to the survivor."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def merged_pair():
    suf = uuid4().hex[:8]
    with SessionLocal() as db:
        ent = Entity(entity_type="commercial", slug=f"merge-ent-{suf}",
                     name=f"Merge Test {suf}", source="test-merge")
        db.add(ent)
        db.flush()
        keep = Provider(provider_name=f"Merge Keep {suf}", category="restaurant",
                        slug=f"merge-keep-{suf}", google_place_id=f"pid-{suf}",
                        is_active=True, draft=False, source="test-merge", entity_id=ent.id)
        dup = Provider(provider_name=f"Merge Keep {suf}", category="restaurant",
                       slug=f"merge-dup-{suf}", is_active=False, draft=False,
                       source="test-merge",
                       attributes={"merged_into_slug": f"merge-keep-{suf}"})
        db.add_all([keep, dup])
        db.commit()
    try:
        yield f"merge-keep-{suf}", f"merge-dup-{suf}"
    finally:
        with SessionLocal() as db:
            for p in db.scalars(select(Provider).where(Provider.source == "test-merge")).all():
                db.delete(p)
            for e in db.scalars(select(Entity).where(Entity.source == "test-merge")).all():
                db.delete(e)
            db.commit()


def test_merged_slug_301s_to_survivor(client: TestClient, merged_pair) -> None:
    keep, dup = merged_pair
    r = client.get(f"/provider/{dup}", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == f"/provider/{keep}"


def test_survivor_still_serves(client: TestClient, merged_pair) -> None:
    keep, _ = merged_pair
    r = client.get(f"/provider/{keep}")
    assert r.status_code == 200


def test_plain_inactive_without_merge_marker_still_404s(client: TestClient) -> None:
    suf = uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(provider_name=f"Inactive {suf}", category="restaurant",
                     slug=f"inactive-{suf}", is_active=False, draft=False,
                     source="test-merge2")
        db.add(p)
        db.commit()
    try:
        r = client.get(f"/provider/inactive-{suf}", follow_redirects=False)
        assert r.status_code == 404
    finally:
        with SessionLocal() as db:
            for p in db.scalars(select(Provider).where(Provider.source == "test-merge2")).all():
                db.delete(p)
            db.commit()
