"""WS13 / M18 — local-first news sectioning.

The pure classifier (§8 render examples) plus the homepage contract: the news
ticker must never surface wire/nation/lifestyle syndication ("Pringles Pop Dog
Buns") while `/news` keeps every section for its tabs.
"""

from __future__ import annotations

import pytest

from app.conditions.cache import upsert_source
from app.db.database import SessionLocal
from app.news.sections import (
    SECTION_BEYOND,
    SECTION_CITY_HALL,
    SECTION_LOCAL,
    SECTION_OPINION,
    news_section,
)
from app.news.store import SOURCE_NEWS_LOCAL, page_view, ticker_view


# ── pure classifier (§8 examples) ────────────────────────────────────────────
@pytest.mark.parametrize("source,url,expected", [
    ("news_herald", "https://havasunews.com/news/local/island-fire-arrest/", SECTION_LOCAL),
    ("news_herald", "https://havasunews.com/news/nation/florida-alligator/", SECTION_BEYOND),
    ("news_herald", "https://havasunews.com/lifestyle/pringles-pop-dog-buns/", SECTION_BEYOND),
    ("news_herald", "https://havasunews.com/business/crypto-prices-july-6/", SECTION_BEYOND),
    ("news_herald", "https://havasunews.com/opinion/socialist-lies/", SECTION_OPINION),
    ("lhc_newsflash", "https://lhcaz.gov/CivicAlerts.aspx?AID=123", SECTION_CITY_HALL),
    ("river_scene_news", "https://riverscenemagazine.com/2026/07/fourth-of-july/", SECTION_LOCAL),
    ("mcso_press", "https://mohavecounty.us/press/arrest-made/", SECTION_LOCAL),
    # a bare News-Herald story with no section path → Local
    ("news_herald", "https://havasunews.com/some-headline/", SECTION_LOCAL),
])
def test_news_section_routing(source: str, url: str, expected: str) -> None:
    assert news_section(source, url) == expected


def test_city_source_is_city_hall_regardless_of_path() -> None:
    assert news_section("lhc_newsflash", "https://x/lifestyle/whatever/") == SECTION_CITY_HALL


def test_news_section_never_raises_on_junk_url() -> None:
    assert news_section("news_herald", None) == SECTION_LOCAL
    assert news_section(None, None) == SECTION_LOCAL


# ── homepage contract (DB-backed) ────────────────────────────────────────────
_ITEMS = [
    {"source": "news_herald", "title": "ZZ Island fire suspect arrested",
     "url": "https://havasunews.com/news/local/island-fire/", "published_at": None},
    {"source": "news_herald", "title": "ZZ Pringles debuts Pop Dog Buns",
     "url": "https://havasunews.com/lifestyle/pringles/", "published_at": None},
    {"source": "lhc_newsflash", "title": "ZZ Milling and paving on Acoma",
     "url": "https://lhcaz.gov/CivicAlerts.aspx?AID=1", "published_at": None},
]


def _seed_news() -> None:
    with SessionLocal() as db:
        upsert_source(db, SOURCE_NEWS_LOCAL, {"items": _ITEMS})
        db.commit()


def _clear_news() -> None:
    with SessionLocal() as db:
        upsert_source(db, SOURCE_NEWS_LOCAL, {"items": []})
        db.commit()


def test_homepage_ticker_drops_beyond_but_page_keeps_it() -> None:
    _seed_news()
    try:
        with SessionLocal() as db:
            ticker_titles = [i["title"] for i in ticker_view(db).items]
            page_titles = [i["title"] for i in page_view(db).items]
        # The homepage module drops the wire/lifestyle "Pringles" item...
        assert "ZZ Pringles debuts Pop Dog Buns" not in ticker_titles
        assert "ZZ Island fire suspect arrested" in ticker_titles
        assert "ZZ Milling and paving on Acoma" in ticker_titles  # City Hall stays
        # ...but /news keeps every section (its tabs need Beyond Havasu).
        assert "ZZ Pringles debuts Pop Dog Buns" in page_titles
    finally:
        _clear_news()


def test_view_items_carry_section_label() -> None:
    _seed_news()
    try:
        with SessionLocal() as db:
            items = {i["title"]: i for i in page_view(db).items}
        assert items["ZZ Pringles debuts Pop Dog Buns"]["section"] == SECTION_BEYOND
        assert items["ZZ Milling and paving on Acoma"]["section"] == SECTION_CITY_HALL
        assert items["ZZ Milling and paving on Acoma"]["section_label"] == "City Hall"
    finally:
        _clear_news()
