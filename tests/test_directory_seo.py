"""B2: the /categories directory landing owns the "Lake Havasu City directory"
intent — a single clean H1, an intent-matching title + bounded meta description,
links to every department, and valid CollectionPage + ItemList JSON-LD.

Style mirrors tests/test_lake_seo.py / tests/test_lake_directory.py (node-free,
deterministic gates that ride the pytest job).
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


@pytest.fixture
def directory_html(seeded_nav_departments) -> str:
    """Render /categories with a few real departments seeded (so the index and
    its ItemList are non-empty)."""
    r = TestClient(app).get("/categories")
    assert r.status_code == 200
    return r.text


def _ld_blocks(html: str) -> list[dict]:
    return [json.loads(m.group(1)) for m in _LD_RE.finditer(html)]


def _collection_page(html: str) -> dict:
    return next(b for b in _ld_blocks(html) if b.get("@type") == "CollectionPage")


def test_directory_has_single_intent_h1(directory_html: str) -> None:
    assert directory_html.count("<h1") == 1
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", directory_html, re.S)
    assert h1 is not None
    assert "Lake Havasu City directory" in h1.group(1)


def test_directory_title_targets_intent(directory_html: str) -> None:
    title = re.search(r"<title>(.*?)</title>", directory_html, re.S)
    assert title is not None
    assert "Lake Havasu City directory" in title.group(1)


def test_directory_meta_description_present_and_bounded(directory_html: str) -> None:
    m = re.search(r'<meta name="description" content="([^"]*)"', directory_html)
    assert m is not None
    desc = m.group(1)
    assert 50 <= len(desc) <= 320  # substantive but within SERP snippet bounds


def test_directory_collectionpage_schema_is_rich(directory_html: str) -> None:
    cp = _collection_page(directory_html)
    assert cp["name"] == "Lake Havasu City directory"
    assert cp.get("description")
    assert cp["url"].startswith("http")
    assert cp["isPartOf"]["@type"] == "WebSite"
    assert cp["about"]["name"] == "Lake Havasu City"
    assert cp["about"]["address"]["addressRegion"] == "AZ"


def test_directory_itemlist_counts_and_links_departments(directory_html: str) -> None:
    cp = _collection_page(directory_html)
    il = cp["mainEntity"]
    assert il["@type"] == "ItemList"
    items = il["itemListElement"]
    # numberOfItems is honest (equals the rendered list) and non-empty.
    assert il["numberOfItems"] == len(items)
    assert len(items) >= 1
    for item in items:
        assert item["name"]
        assert item["url"].startswith("http")
        assert "/categories/" in item["url"]


def test_directory_links_every_seeded_department(
    directory_html: str, seeded_nav_departments
) -> None:
    for slug in seeded_nav_departments["departments"]:
        assert f"/categories/{slug}" in directory_html
