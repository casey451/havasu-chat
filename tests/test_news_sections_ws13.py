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
    NON_LOCAL_SECTIONS,
    SECTION_BEYOND,
    SECTION_CITY_HALL,
    SECTION_LOCAL,
    SECTION_OPINION,
    has_local_signal,
    is_trusted_local_source,
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


# ── homepage local-only gate (2026-07-08 re-audit item 4) ────────────────────
# The homepage "Local news" module ran opinion columns ("Dave Eaton: World Cup
# vs. TDS") and bare-URL national wire ("Unstable NYC building…", "Half of
# Americans support placing the Ten Commandments…"). Opinion now joins Beyond in
# NON_LOCAL_SECTIONS, and a catch-all Local item from a syndication-prone source
# must carry a Havasu / immediate-region signal to reach /home.
def test_opinion_and_beyond_are_non_local_but_local_and_city_are_not() -> None:
    assert SECTION_OPINION in NON_LOCAL_SECTIONS
    assert SECTION_BEYOND in NON_LOCAL_SECTIONS
    assert SECTION_LOCAL not in NON_LOCAL_SECTIONS
    assert SECTION_CITY_HALL not in NON_LOCAL_SECTIONS


@pytest.mark.parametrize("url,title,expected", [
    # local URL path or Havasu-proper mention → keep
    ("https://havasunews.com/news/local/island-fire/", "Fire suspect arrested", True),
    ("https://havasunews.com/some-headline/", "Lake Havasu council approves budget", True),
    ("https://havasunews.com/from-x-a-look-at-lake-havasu/", "A look at LHC courts", True),
    ("https://havasunews.com/mohave-county-fair-returns/", "Mohave County Fair returns", True),
    # bare-URL national wire / statewide, no Havasu signal → drop
    ("https://havasunews.com/unstable-nyc-building/", "Unstable NYC building may collapse", False),
    ("https://havasunews.com/half-of-americans-ten-cmd/", "Half of Americans support Ten Commandments", False),
    ("https://havasunews.com/news/arizona/doj-warns/", "DOJ warns Arizona election officials", False),
])
def test_has_local_signal(url: str, title: str, expected: bool) -> None:
    assert has_local_signal(url, title) is expected


def test_is_trusted_local_source() -> None:
    assert is_trusted_local_source("lhc_newsflash")
    assert is_trusted_local_source("river_scene_news")
    assert is_trusted_local_source("MCSO_PRESS")  # case-insensitive
    assert not is_trusted_local_source("news_herald")
    assert not is_trusted_local_source(None)


_LEAK_ITEMS = [
    {"source": "news_herald", "title": "ZZ Lake Havasu council approves budget",
     "url": "https://havasunews.com/lhc-council-budget/", "published_at": None},
    {"source": "news_herald", "title": "ZZ Unstable NYC building threatening to collapse",
     "url": "https://havasunews.com/unstable-nyc-building/", "published_at": None},
    {"source": "news_herald", "title": "ZZ Dave Eaton: World Cup vs. TDS",
     "url": "https://havasunews.com/opinion/dave-eaton-world-cup/", "published_at": None},
]


def _seed_items(items: list[dict]) -> None:
    with SessionLocal() as db:
        upsert_source(db, SOURCE_NEWS_LOCAL, {"items": items})
        db.commit()


def test_homepage_drops_opinion_and_bare_url_wire_but_page_keeps_them() -> None:
    _seed_items(_LEAK_ITEMS)
    try:
        with SessionLocal() as db:
            ticker = [i["title"] for i in ticker_view(db).items]
            page = [i["title"] for i in page_view(db).items]
        # homepage: genuine local kept; opinion + bare-URL wire dropped
        assert "ZZ Lake Havasu council approves budget" in ticker
        assert "ZZ Unstable NYC building threatening to collapse" not in ticker
        assert "ZZ Dave Eaton: World Cup vs. TDS" not in ticker
        # /news keeps every section for its tabs
        assert "ZZ Unstable NYC building threatening to collapse" in page
        assert "ZZ Dave Eaton: World Cup vs. TDS" in page
    finally:
        _clear_news()
