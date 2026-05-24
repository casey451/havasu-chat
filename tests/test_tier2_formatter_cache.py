"""Tier 2 formatter cache (Lane B-2)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.chat import tier2_cache
from app.db.database import SessionLocal


@pytest.fixture
def db_session() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_lookup_formatter_returns_none_on_miss(db_session: Session) -> None:
    out = tier2_cache.lookup_formatter(db_session, "b2 sentinel formatter miss", [{"id": 1}])
    assert out is None


def test_store_then_lookup_formatter_roundtrip(db_session: Session) -> None:
    rows = [{"id": "abc", "name": "Mudshark Brewery", "phone": "928-123-4567"}]
    tier2_cache.store_formatter(db_session, "where can i eat", rows, "Try Mudshark.")
    hit = tier2_cache.lookup_formatter(db_session, "where can i eat", rows)
    assert hit == "Try Mudshark."


def test_formatter_cache_keyed_on_rows_payload(db_session: Session) -> None:
    """Same query, different row payloads -- different cache entries."""
    rows_morning = [{"id": "a", "name": "Cafe Open AM"}]
    rows_evening = [{"id": "b", "name": "Bar Open PM"}]
    tier2_cache.store_formatter(db_session, "what is open", rows_morning, "Cafe Open AM serves until 11.")
    hit_morning = tier2_cache.lookup_formatter(db_session, "what is open", rows_morning)
    hit_evening = tier2_cache.lookup_formatter(db_session, "what is open", rows_evening)
    assert hit_morning is not None
    assert hit_evening is None, "different rows payload must be a cache miss"


def test_store_formatter_skips_when_text_empty(db_session: Session) -> None:
    tier2_cache.store_formatter(db_session, "b2 empty text guard", [{"id": 1}], "")
    out = tier2_cache.lookup_formatter(db_session, "b2 empty text guard", [{"id": 1}])
    assert out is None
