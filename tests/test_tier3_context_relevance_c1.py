"""C1: entity-less Tier 3 context must be ranked by query relevance.

The old path discarded the query and fed a fixed alphabetical-verified slice of
providers to the LLM, so open-ended turns always saw the same 10 rows.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.chat import context_builder as cb
from app.db.database import SessionLocal
from app.db.models import Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_query_tokens_drops_stopwords_and_short_tokens() -> None:
    assert cb._query_tokens("what are the best tacos near me") == ["tacos"]
    assert cb._query_tokens("") == []
    assert cb._query_tokens(None) == []


def test_provider_relevance_counts_token_hits() -> None:
    p = Provider(provider_name="Taco Town", category="restaurant")
    assert cb._provider_relevance(p, ["tacos"]) == 0  # "tacos" != "taco"
    assert cb._provider_relevance(p, ["taco", "town"]) == 2
    assert cb._provider_relevance(p, []) == 0


def test_fetch_provider_rows_ranks_query_match_first(db: Session) -> None:
    # Unique token so only this provider scores; everything else relevance 0.
    token = f"zqx{uuid.uuid4().hex[:8]}"
    name = f"{token} Plumbing"
    p = Provider(
        provider_name=name,
        slug=f"prov-{uuid.uuid4().hex[:10]}",
        category="home_services",
        source="test-c1",
        draft=False,
        is_active=True,
        verified=False,
    )
    db.add(p)
    db.commit()
    try:
        rows = cb._fetch_provider_rows(db, None, query=f"looking for a {token}")
        assert rows, "expected at least the seeded provider"
        assert rows[0].provider_name == name
    finally:
        db.execute(delete(Provider).where(Provider.provider_name == name))
        db.commit()
