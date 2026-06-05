"""Admin "miscategorized?" review-list tests (category patrol)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from app.admin.category_flags_html import flagged_provider_count
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


def _clear_all_flags() -> None:
    with SessionLocal() as db:
        db.execute(update(Provider).values(category_flagged_at=None))
        db.commit()


def _make_provider(
    *, source: str, name: str, primary: str, confidence: float | None, flagged: bool
) -> str:
    with SessionLocal() as db:
        p = Provider(
            provider_name=name,
            category="legacy",
            primary_category=primary,
            source=source,
            category_confidence=confidence,
            category_flagged_at=datetime.now(UTC) if flagged else None,
        )
        db.add(p)
        db.commit()
        return p.id


@pytest.fixture
def tmp_source() -> str:
    source = f"test-flags-{uuid.uuid4().hex[:8]}"
    yield source
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.source == source))
        db.commit()


def test_miscategorized_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/providers/miscategorized", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_empty_state_renders(client: TestClient) -> None:
    _clear_all_flags()
    _login(client)
    r = client.get("/admin/providers/miscategorized")
    assert r.status_code == 200
    assert "No providers flagged as miscategorized" in r.text
    assert "Possibly miscategorized" in r.text


def test_lists_flagged_excludes_unflagged_and_sorts(client: TestClient, tmp_source: str) -> None:
    _clear_all_flags()
    _make_provider(
        source=tmp_source, name="ZLowConf Diner", primary="pets", confidence=0.80, flagged=True
    )
    _make_provider(
        source=tmp_source, name="AHighConf Law", primary="shopping-essentials",
        confidence=0.95, flagged=True,
    )
    _make_provider(
        source=tmp_source, name="Unflagged Cafe", primary="pets", confidence=None, flagged=False
    )
    _login(client)
    r = client.get("/admin/providers/miscategorized")
    assert r.status_code == 200
    body = r.text
    assert "AHighConf Law" in body
    assert "ZLowConf Diner" in body
    assert "Unflagged Cafe" not in body
    # Highest confidence first regardless of name.
    assert body.index("AHighConf Law") < body.index("ZLowConf Diner")


def test_resolve_clears_flag(client: TestClient, tmp_source: str) -> None:
    pid = _make_provider(
        source=tmp_source, name="Fixme Co", primary="pets", confidence=0.9, flagged=True
    )
    _login(client)
    r = client.post(
        f"/admin/providers/{pid}/resolve-category-flag", follow_redirects=False
    )
    assert r.status_code == 303
    with SessionLocal() as db:
        got = db.get(Provider, pid)
        assert got.category_flagged_at is None


def test_resolve_requires_auth(client: TestClient, tmp_source: str) -> None:
    pid = _make_provider(
        source=tmp_source, name="Guarded Co", primary="pets", confidence=0.9, flagged=True
    )
    client.cookies.clear()
    r = client.post(
        f"/admin/providers/{pid}/resolve-category-flag", follow_redirects=False
    )
    assert r.status_code == 302
    # Flag must remain untouched.
    with SessionLocal() as db:
        assert db.get(Provider, pid).category_flagged_at is not None


def test_flagged_provider_count(tmp_source: str) -> None:
    _clear_all_flags()
    _make_provider(source=tmp_source, name="A", primary="pets", confidence=0.9, flagged=True)
    _make_provider(source=tmp_source, name="B", primary="pets", confidence=0.8, flagged=True)
    _make_provider(source=tmp_source, name="C", primary="pets", confidence=None, flagged=False)
    with SessionLocal() as db:
        assert flagged_provider_count(db) == 2


def test_nav_link_present(client: TestClient) -> None:
    _login(client)
    r = client.get("/admin/providers/miscategorized")
    assert "/admin/providers/miscategorized" in r.text
    assert "Miscategorized" in r.text
