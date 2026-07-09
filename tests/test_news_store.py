"""Regression coverage for app.news.store — the cache row is naive-UTC, but the
/news router reads it with a tz-aware ``now`` (now_lake_havasu). The store must
normalize so naive-vs-aware subtraction in read_source never crashes the page."""

from __future__ import annotations

from app.conditions.cache import upsert_source
from app.conditions.constants import SOURCE_NEWS_LOCAL
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.news import store

_SEED = {
    "items": [
        {
            "source": "news_herald",
            "source_label": "Havasu News-Herald",
            "title": "Council approves new lakefront park",
            # local URL path so it clears the homepage local-only gate (this test
            # exercises tz handling, not sectioning)
            "url": "https://havasunews.com/news/local/lakefront-park/",
            "published_at": "2026-06-29T12:00:00",
            "keywords": ["park"],
        }
    ]
}


def _seed() -> None:
    db = next(get_db())
    try:
        upsert_source(db, SOURCE_NEWS_LOCAL, _SEED)
        db.commit()
    finally:
        db.close()


def test_page_view_survives_tz_aware_now() -> None:
    """The /news router passes now_lake_havasu() (tz-aware) — page_view must not
    raise on naive-vs-aware datetime subtraction in read_source/_is_stale."""
    _seed()
    db = next(get_db())
    try:
        view = store.page_view(db, now=now_lake_havasu())
    finally:
        db.close()
    assert view.items, "seeded headline should render"
    assert view.items[0]["title"] == "Council approves new lakefront park"


def test_ticker_view_survives_tz_aware_now() -> None:
    _seed()
    db = next(get_db())
    try:
        view = store.ticker_view(db, now=now_lake_havasu())
    finally:
        db.close()
    assert view.items, "seeded headline should render in the ticker"
