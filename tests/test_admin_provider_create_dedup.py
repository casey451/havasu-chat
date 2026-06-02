"""Admin operator-entry create: duplicate warn-don't-block guard (Item D).

The admin provider-create POST is the only provider write path with no
reconcile -- an operator could silently create a VISIBLE duplicate. These tests
cover the "warn, then confirm" behavior added on top of reconcile_hit:

  * a create that matches an existing provider re-renders the form with a
    duplicate warning instead of writing the row, and
  * resubmitting with the confirm flag creates it anyway (stays visible).

Run from the owner's terminal: python -m pytest tests/test_admin_provider_create_dedup.py -q

These routes commit (no rollback harness), so each test cleans up the rows it
creates -- providers AND their entities -- in a finally block. Mirrors the
harness in tests/test_admin_provider_merge_review.py.
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


def _make_existing(name: str) -> str:
    """Create one live provider with *name*; return its id."""
    with SessionLocal() as s:
        p = Provider(
            provider_name=name,
            category="eat-drink",
            slug=derive_provider_slug(s, name),
            source="go_lake_havasu",
            draft=False,
            is_active=True,
        )
        s.add(p)
        create_provider_and_entity(s, p)
        s.commit()
        return p.id


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


def _count_providers(name: str) -> int:
    with SessionLocal() as s:
        return len(s.scalars(select(Provider).where(Provider.provider_name == name)).all())


def test_create_matching_name_warns_and_does_not_write(admin_client):
    name = f"CreateDup {uuid.uuid4().hex[:8]}"
    _make_existing(name)
    try:
        resp = admin_client.post(
            "/admin/providers",
            data={"provider_name": name, "category": "eat-drink"},
            follow_redirects=False,
        )
        # Warning re-render is a 200 form, NOT a 303 redirect (no write happened).
        assert resp.status_code == 200
        assert "Possible duplicate" in resp.text
        assert "Create anyway" in resp.text
        assert 'name="confirm_create_duplicate"' in resp.text
        # Still exactly the one existing provider -- nothing new written.
        assert _count_providers(name) == 1
    finally:
        _cleanup(name)


def test_create_with_confirm_flag_creates_duplicate(admin_client):
    name = f"CreateDup {uuid.uuid4().hex[:8]}"
    _make_existing(name)
    try:
        resp = admin_client.post(
            "/admin/providers",
            data={
                "provider_name": name,
                "category": "eat-drink",
                "confirm_create_duplicate": "1",
            },
            follow_redirects=False,
        )
        # Confirmed -> created (redirect) and visible (draft=False).
        assert resp.status_code == 303
        assert _count_providers(name) == 2
        with SessionLocal() as s:
            new = s.scalars(
                select(Provider).where(
                    Provider.provider_name == name, Provider.source == "admin"
                )
            ).one()
            assert new.draft is False
            assert new.is_active is True
    finally:
        _cleanup(name)


def test_create_matching_website_warns_when_contact_tier_on(admin_client):
    # Contact (website) tier is OFF by default; when an operator opts in via
    # INGEST_CONTACT_TIER_ENABLED, a different-named entry sharing a website
    # domain with an existing provider must also warn.
    name = f"CreateWebExisting {uuid.uuid4().hex[:8]}"
    new_name = f"CreateWebNew {uuid.uuid4().hex[:8]}"
    site = f"https://{uuid.uuid4().hex[:10]}.example.com"
    with SessionLocal() as s:
        p = Provider(
            provider_name=name,
            category="eat-drink",
            slug=derive_provider_slug(s, name),
            source="go_lake_havasu",
            website=site,
            draft=False,
            is_active=True,
        )
        s.add(p)
        create_provider_and_entity(s, p)
        s.commit()
    prev = os.environ.get("INGEST_CONTACT_TIER_ENABLED")
    os.environ["INGEST_CONTACT_TIER_ENABLED"] = "1"
    try:
        resp = admin_client.post(
            "/admin/providers",
            data={"provider_name": new_name, "category": "eat-drink", "website": site},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Possible duplicate" in resp.text
        assert _count_providers(new_name) == 0
    finally:
        if prev is None:
            os.environ.pop("INGEST_CONTACT_TIER_ENABLED", None)
        else:
            os.environ["INGEST_CONTACT_TIER_ENABLED"] = prev
        _cleanup(name)
        _cleanup(new_name)


def test_create_novel_name_writes_directly(admin_client):
    name = f"CreateNovel {uuid.uuid4().hex[:8]}"
    try:
        resp = admin_client.post(
            "/admin/providers",
            data={"provider_name": name, "category": "eat-drink"},
            follow_redirects=False,
        )
        # No existing match -> reconcile says insert -> created without confirm.
        assert resp.status_code == 303
        assert _count_providers(name) == 1
    finally:
        _cleanup(name)
