"""Phase 3a — the Lake Ink & Brass directory (index / category / department / trade).

Covers the reusable listing card + the rich category template rendered directly
with sample data (the live /categories/{slug} routing needs seeded taxonomy, so
direct render is the deterministic check), the index page on the flag,
desert-default, CollectionPage/ItemList schema, template validity, and a11y.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader
from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.categories.router import templates as _cat_templates
from app.main import app

_TPL = Path(__file__).resolve().parents[1] / "app" / "templates"


def _render_card(card: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(_TPL)), autoescape=True)
    return env.get_template("components/lake_biz_card.html").render(card=card)


def _sample_card() -> dict:
    return {
        "slug": "mudshark", "name": "Mudshark Brewery", "image_url": None,
        "is_open": True, "is_sponsored": True, "ad_headline": None, "has_reviews": True,
        "rating": "4.7", "review_count": 210, "area": "Uptown", "distance_hint": None,
        "subcategory": "brewpub", "phone_tel": "19285550100",
        "directions_url": "https://maps.example/x", "website": None,
    }


def _fake_request(path: str = "/categories/eat-and-drink") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def test_card_provider_link_sponsored_and_open() -> None:
    h = _render_card(_sample_card())
    assert "/provider/mudshark" in h
    assert "Mudshark Brewery" in h and "Sponsored" in h
    # v4.5 PR-4: the rating is an SVG star icon + number (no ★ glyph — zero emoji).
    assert 'class="star"' in h and "4.7" in h and "Open now" in h
    assert "tel:19285550100" in h
    # No image block at all when there's no photo (v45 §0: real photo or nothing —
    # the old ph--art monogram placeholder is gone).
    assert 'class="bph"' not in h and "ph--art" not in h and ">M<" not in h


def test_card_place_without_slug_links_out() -> None:
    h = _render_card({
        "slug": None, "name": "Aquatic Center", "image_url": None, "is_open": None,
        "is_sponsored": False, "ad_headline": None, "has_reviews": False, "rating": None,
        "review_count": 0, "area": None, "distance_hint": None, "subcategory": "pool",
        "phone_tel": None, "directions_url": None, "website": "https://example.com/pool",
    })
    assert 'href="https://example.com/pool"' in h
    assert "New / few reviews" in h
    assert "/provider/" not in h


def test_lake_categories_index() -> None:
    b = TestClient(app).get("/categories?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_redesign.css" in b  # v4.5 PR-4: the v4 shell stylesheet
    assert b.count("<h1") == 1
    assert '"@type": "CollectionPage"' in b
    checker = _A11yChecker()
    checker.feed(b)
    assert not checker.finish()


def test_all_lake_directory_templates_are_valid() -> None:
    for name in ("categories_index_lake.html", "category_sandstone_lake.html",
                 "category_department_lake.html", "category_trade_lake.html",
                 "components/lake_biz_card.html"):
        _cat_templates.env.get_template(name)  # parses + compiles (raises on error)


def test_lake_category_browse_renders_with_sample_data() -> None:
    ctx = {
        "category_label": "Eat & Drink", "category_one_liner": "Tacos to steakhouses.",
        "category_count": 2, "page": 1, "total_pages": 1, "prev_url": None, "next_url": None,
        "category_cards": [_sample_card()], "trade_links": [],
        "subcat_chips": [{"slug": "mexican", "label": "Mexican"}], "cuisine_chips": [],
        "active_cuisine": None, "all_chip_url": "/categories/eat-and-drink",
        "facets": {"subcategory": None, "open_now": False, "top_rated": False, "sort": "favorites", "cuisine": None},
        "facet_href": lambda **kw: "/categories/eat-and-drink", "sort_note": "",
        "active_filter_labels": [], "clear_filters_url": "/categories/eat-and-drink",
        "page_summary": "Showing 2", "sponsored": None,
    }
    html = _cat_templates.env.get_template("category_sandstone_lake.html").render(
        request=_fake_request(), **ctx
    )
    assert 'data-theme="lake"' in html
    assert "Eat &amp; Drink" in html
    assert "/provider/mudshark" in html  # the card include rendered
    assert "Mexican" in html  # subcategory chip
    assert 'class="askstrip"' in html
    assert '"@type": "CollectionPage"' in html
    assert html.count("<h1") == 1
    checker = _A11yChecker()
    checker.feed(html)
    assert not checker.finish()
