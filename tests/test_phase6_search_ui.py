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
    # Lake hero search composer posts to the concierge.
    assert 'class="search" role="search" action="/chat"' in r.text
    assert 'id="rd-search"' in r.text
    assert 'role="search"' in r.text
    assert 'name="q"' in r.text
    assert "Ask Hava" in r.text
    assert "<!-- search-bar-include -->" not in r.text


def test_category_header_has_hava_search(client: TestClient) -> None:
    r = client.get("/lake-havasu/restaurants")
    assert r.status_code == 200
    # Lake category page renders its own page header; search lives on the home
    # hero, not the category header (no per-page search_bar.js).
    assert 'class="pagehead"' in r.text
    assert "search_bar.js" not in r.text


def test_search_css_and_js_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "app/static/js/search_bar.js").is_file()


def test_api_search_regression_guard(client: TestClient) -> None:
    r = client.get("/api/search", params={"q": "test", "limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "next_cursor" in data
