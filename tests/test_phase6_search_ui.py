"""Phase 6.4 — search bar UI distinct from Ask Hava."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_home_hero_search_bar_anchor_and_attributes(client: TestClient) -> None:
    r = client.get("/home")
    assert r.status_code == 200
    assert "<!-- search-bar-include -->" in r.text
    assert 'data-hava-search' in r.text
    assert 'role="search"' in r.text
    assert 'aria-label="Search listings"' in r.text
    assert "hava-search-input" in r.text


def test_home_ask_hava_distinct_from_search(client: TestClient) -> None:
    r = client.get("/home")
    assert "hava-ask-hava-btn" in r.text
    assert 'class="composer"' in r.text
    assert "hava-search-submit" in r.text


def test_category_header_has_hava_search(client: TestClient) -> None:
    r = client.get("/category/eat-drink")
    assert r.status_code == 200
    assert "hava-search-input" in r.text
    assert "search_bar.js" in r.text


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
