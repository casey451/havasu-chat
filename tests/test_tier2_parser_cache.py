"""Tier 2 parser cache (Lane B-2)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.chat import tier2_cache
from app.chat.tier2_schema import Tier2Filters
from app.db.database import SessionLocal


@pytest.fixture
def db_session() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_lookup_parser_returns_none_on_miss(db_session: Session) -> None:
    out = tier2_cache.lookup_parser(db_session, "b2 sentinel parser miss", "2026-05-24")
    assert out is None


def test_store_then_lookup_parser_roundtrip(db_session: Session) -> None:
    filters = Tier2Filters(category="restaurant", open_now=True, parser_confidence=0.9, fallback_to_tier3=False)
    tier2_cache.store_parser(db_session, "b2 parser roundtrip", "2026-05-24", filters)
    hit = tier2_cache.lookup_parser(db_session, "b2 parser roundtrip", "2026-05-24")
    assert hit is not None
    assert hit.category == "restaurant"
    assert hit.open_now is True
    assert hit.parser_confidence == 0.9


def test_parser_cache_key_includes_today_iso(db_session: Session) -> None:
    """Same query, different dates -- different cache entries (today_iso matters)."""
    filters_may = Tier2Filters(category="restaurant", open_now=True, parser_confidence=0.9, fallback_to_tier3=False)
    tier2_cache.store_parser(db_session, "may 8 events", "2026-05-08", filters_may)
    hit_same_day = tier2_cache.lookup_parser(db_session, "may 8 events", "2026-05-08")
    hit_next_year = tier2_cache.lookup_parser(db_session, "may 8 events", "2027-05-08")
    assert hit_same_day is not None
    assert hit_next_year is None, "different today_iso must be a cache miss"


def test_store_parser_skips_when_filters_is_none(db_session: Session) -> None:
    tier2_cache.store_parser(db_session, "b2 none guard", "2026-05-24", None)  # type: ignore[arg-type]
    out = tier2_cache.lookup_parser(db_session, "b2 none guard", "2026-05-24")
    assert out is None, "store_parser must not persist None filters"
