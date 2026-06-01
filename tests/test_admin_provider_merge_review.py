"""Admin duplicate-merge review UI tests (Item C UI).

Run from the owner's terminal: python -m pytest tests/test_admin_provider_merge_review.py -q

These routes commit (no rollback harness), so each test cleans up the rows it
creates -- providers AND their entities -- in a finally block.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Entity, Provider
from app.db.seed_helpers import derive_provider_slug
from app.main import app

_LAT = 34.4839
_LNG = -114.3225


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


@pytest.fixture
def admin_client() -> TestClient:
    client = TestClient(app)
    client.cookies.clear()
    _login(client)
    return client


def _make_pair(name: str) -> tuple[str, str]:
    """Create two live same-name providers at the same point -> a geo+name pair."""
    with SessionLocal() as s:
        ids = []
        for _ in range(2):
            p = Provider(
                provider_name=name,
                category="eat-drink",
                slug=derive_provider_slug(s, name),
                source="go_lake_havasu",
                lat=_LAT,
                lng=_LNG,
                draft=False,
                is_active=True,
            )
            s.add(p)
            create_provider_and_entity(s, p)
            s.flush()
            ids.append(p.id)
        s.commit()
        return ids[0], ids[1]


def _cleanup(name: str) -> None:
    with SessionLocal() as s:
        provs = s.scalars(select(Provider).where(Provider.provider_name == name)).all()
        ent_ids = [p.entity_id for p in provs if p.entity_id]
        for p in provs:
            s.delete(p)
        s.flush()
        for ent in s.scalars(select(Entity).where(Entity.id.in_(ent_ids))).all():
            s.delete(ent)
        s.commit()


def test_duplicates_page_requires_admin():
    client = TestClient(app)
    # No admin cookie -> redirect to login (guard), do not follow.
    resp = client.get("/admin/providers/duplicates", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert "/admin/login" in resp.headers.get("location", "")


def test_duplicates_lists_preview_and_merges(admin_client):
    name = f"MergeUI Dup {uuid.uuid4().hex[:8]}"
    keep_id, dup_id = _make_pair(name)
    try:
        # 1. The pair shows on the list page.
        resp = admin_client.get("/admin/providers/duplicates")
        assert resp.status_code == 200
        assert name in resp.text

        # 2. Preview is a dry-run: nothing retired yet.
        resp = admin_client.post(
            "/admin/providers/duplicates/preview",
            data={"keep_id": keep_id, "dup_id": dup_id},
        )
        assert resp.status_code == 200
        assert "Confirm merge" in resp.text
        with SessionLocal() as s:
            assert s.get(Provider, dup_id).is_active is True

        # 3. Confirm merge: dup retired (inactive + draft), keep stays live.
        resp = admin_client.post(
            "/admin/providers/duplicates/merge",
            data={"keep_id": keep_id, "dup_id": dup_id},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        with SessionLocal() as s:
            dup = s.get(Provider, dup_id)
            keep = s.get(Provider, keep_id)
            assert dup.is_active is False and dup.draft is True
            assert keep.is_active is True and keep.draft is False
    finally:
        _cleanup(name)


def test_merge_bad_pair_returns_400(admin_client):
    name = f"MergeUI Solo {uuid.uuid4().hex[:8]}"
    keep_id, _dup_id = _make_pair(name)
    try:
        resp = admin_client.post(
            "/admin/providers/duplicates/merge",
            data={"keep_id": keep_id, "dup_id": "no-such-id"},
        )
        assert resp.status_code == 400
        assert "Cannot merge" in resp.text
    finally:
        _cleanup(name)
