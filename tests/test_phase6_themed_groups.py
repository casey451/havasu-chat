"""Phase 6.4 — themed group landing pages."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes import category_pages
from app.groups import themed_groups as tg
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    "slug",
    [
        "eat-drink-group",
        "health-fitness-group",
        "on-the-water-group",
        "home-auto-group",
    ],
)
def test_themed_group_pages_return_200(client: TestClient, slug: str) -> None:
    r = client.get(f"/group/{slug}")
    assert r.status_code == 200
    assert "hava-card" in r.text or "category-stream" in r.text


def test_unknown_group_404(client: TestClient) -> None:
    r = client.get("/group/not-a-group")
    assert r.status_code == 404


def test_health_fitness_group_interleaves_categories(client: TestClient) -> None:
    cats = tg.get_categories_for_group("health-fitness-group")
    assert "health-wellness-care" in cats
    assert "classes-sports-recreation" in cats
    r = client.get("/group/health-fitness-group")
    assert r.status_code == 200
    assert "Health &amp; Fitness" in r.text or "Health & Fitness" in r.text
    assert "health-wellness-care" in r.text


def test_group_sort_default_from_first_category() -> None:
    cats = tg.get_categories_for_group("home-auto-group")
    cfg = category_pages.category_page_config(cats[0])
    assert cfg.sort_default == "editorial_pick"


def test_themed_group_template_assets(client: TestClient) -> None:
    r = client.get("/group/on-the-water-group")
    assert r.status_code == 200
    assert "map.js" in r.text
    assert "search_bar.js" in r.text
    assert "group-accent-water" in r.text
