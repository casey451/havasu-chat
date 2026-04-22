"""Phase 8.0.6 — shared admin Phase 5 nav (contributions, mentions, categories, feedback)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


_NAV_HREFS = (
    "/admin?tab=queue",
    "/admin/contributions",
    "/admin/mentioned-entities",
    "/admin/categories",
    "/admin/analytics",
    "/admin/feedback",
)


@pytest.mark.parametrize(
    "path",
    (
        "/admin/contributions",
        "/admin/mentioned-entities",
        "/admin/categories",
        "/admin/feedback",
    ),
)
def test_phase5_admin_pages_include_full_nav(client: TestClient, path: str) -> None:
    client.cookies.clear()
    _login(client)
    r = client.get(path)
    assert r.status_code == 200
    text = r.text
    for href in _NAV_HREFS:
        assert f'href="{href}"' in text or f"href='{href}'" in text
