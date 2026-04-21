"""Admin category discovery page (Phase 5.6)."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.contribution_store import create_contribution
from app.db.database import SessionLocal
from app.main import app
from app.schemas.contribution import ContributionCreate


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


def test_categories_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/categories", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_categories_authenticated_three_sections(client: TestClient) -> None:
    u = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name=f"CatHint {u}",
                submission_category_hint=f"emerging-{u}",
                source="operator_backfill",
            ),
            None,
        )
    client.cookies.clear()
    _login(client)
    r = client.get("/admin/categories")
    assert r.status_code == 200
    assert "Provider categories" in r.text
    assert "Program activity categories" in r.text
    assert "Pending contribution category hints" in r.text
    with SessionLocal() as db:
        from sqlalchemy import select

        from app.db.models import Contribution

        row = db.scalars(
            select(Contribution).where(Contribution.submission_name == f"CatHint {u}")
        ).first()
        if row:
            db.delete(row)
            db.commit()


def test_categories_shows_pending_hint_row(client: TestClient) -> None:
    u = uuid.uuid4().hex[:8]
    hint = f"pickleball-{u}"
    with SessionLocal() as db:
        create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name=f"HintRow {u}",
                submission_category_hint=hint,
                source="operator_backfill",
            ),
            None,
        )
    _login(client)
    r = client.get("/admin/categories")
    assert r.status_code == 200
    assert hint in r.text
    with SessionLocal() as db:
        from sqlalchemy import select

        from app.db.models import Contribution

        row = db.scalars(select(Contribution).where(Contribution.submission_name == f"HintRow {u}")).first()
        if row:
            db.delete(row)
            db.commit()


def test_categories_provider_counts_reasonable(client: TestClient) -> None:
    _login(client)
    r = client.get("/admin/categories")
    assert r.status_code == 200
    assert "Count" in r.text
    assert "<table>" in r.text
