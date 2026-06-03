"""Phase 6.4 — search bar UI distinct from Ask Hava."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_home_hero_composer_and_ask_hava(client: TestClient) -> None:
    r = client.get("/home")
    assert r.status_code == 200
    assert 'class="searchbox"' in r.text
    assert 'id="home-ask-form"' in r.text
    assert 'action="/chat"' in r.text
    assert 'role="search"' in r.text
    assert 'aria-label="Ask Hava"' in r.text
    assert 'name="q"' in r.text
    assert "Ask Hava" in r.text
    assert "<!-- search-bar-include -->" not in r.text


def test_category_header_has_hava_search(client: TestClient) -> None:
    r = client.get("/categories/eat-drink")
    assert r.status_code == 200
    # Sandstone category page uses the shared editorial header (logo + nav +
    # Explore mega); search lives on the home hero, not the category header.
    assert 'class="cathead wrap"' in r.text
    assert "search_bar.js" not in r.text


def test_search_css_and_js_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "app/static/js/search_bar.js").is_file()
    assert (root / "app/static/styles/components/search.css").is_file()


def test_api_search_regression_guard(client: TestClient) -> None:
    r = client.get("/api/search", params={"q": "test", "limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "next_cursor" in data
