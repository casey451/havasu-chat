"""Hunt 2026-06-10 §4b / PERF-2: category-aware Tier-3 retrieval.

The old Tier-3 relevance scan covered name+category+address only, so
"plumber" / "bowling" / "electrician" — which live in
``google_primary_category`` / ``google_categories`` — were invisible, and
every query paid a full-table Provider scan. These tests pin the new
SQL-candidate pipeline (leaf routing, Google-category needles, token ILIKE,
FTS fallback) and the Google-aware scorer.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.chat import context_builder as cb
from app.db.database import Base
from app.db.models import Category, Entity, EntityCategory, Provider


@pytest.fixture
def mem_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _provider(db: Session, name: str, **kw) -> Provider:
    p = Provider(
        provider_name=name,
        slug=f"p-{uuid4().hex[:10]}",
        category=kw.pop("category", "services"),
        draft=False,
        is_active=True,
        verified=kw.pop("verified", True),
        **kw,
    )
    db.add(p)
    db.flush()
    return p


# --- scorer (§4b: Google fields now visible) ---------------------------------


def test_relevance_sees_google_primary_category() -> None:
    p = Provider(
        provider_name="Joe's Service Co",
        category="home_services",
        google_primary_category="plumber",
    )
    assert cb._provider_relevance(p, ["plumber"]) == 1
    # needle hits score double
    assert cb._provider_relevance(p, ["plumber"], ("plumber",)) == 3


def test_relevance_sees_google_categories_with_underscores() -> None:
    p = Provider(
        provider_name="Havasu Lanes",
        category="entertainment_attractions",
        google_categories=["bowling_alley", "amusement_center"],
    )
    assert cb._provider_relevance(p, ["bowling"]) == 1
    assert cb._provider_relevance(p, [], ("bowling alley",)) == 2


# --- category vocabulary extraction ------------------------------------------


def test_category_vocab_terms_from_conversational_queries() -> None:
    assert cb._category_vocab_terms("what is the best plumber in lake havasu") == ["plumber"]
    assert cb._category_vocab_terms("i need a plumber") == ["plumber"]
    assert "bowling alley" in cb._category_vocab_terms("any bowling alley here")
    assert cb._category_vocab_terms("hello there") == []
    assert cb._category_vocab_terms(None) == []


def test_category_vocab_bigram_suppresses_member_token() -> None:
    terms = cb._category_vocab_terms("bowling alley near me")
    assert terms == ["bowling alley"]  # "bowling" alone is covered by the bigram


def test_needles_expand_through_synonym_groups() -> None:
    needles = cb._category_needles_for_query(["plumber"])
    assert "plumbing" in needles and "plumbers" in needles


# --- retrieval: the three hunt families --------------------------------------


def test_plumber_invisible_in_haystack_is_retrieved(mem_db: Session) -> None:
    # Name/category/address contain no query token — pre-§4b this was invisible.
    target = _provider(
        mem_db,
        "Joe's Service Co",
        category="home_services",
        google_primary_category="plumber",
    )
    _provider(mem_db, "Distractor Cafe", category="cafe")
    for query in (
        "what is the best plumber in lake havasu",
        "i need a plumber",
        "plummbers",  # not spell-corrected here; needle 'plumber' absent — leaf path no, token no
    )[:2]:
        rows = cb._fetch_provider_rows(mem_db, None, query=query)
        assert rows and rows[0].id == target.id, query


def test_bowling_via_google_categories(mem_db: Session) -> None:
    target = _provider(
        mem_db,
        "Havasu Lanes",
        category="entertainment_attractions",
        google_categories=["bowling_alley"],
    )
    _provider(mem_db, "Aaa Verified Distractor")
    rows = cb._fetch_provider_rows(mem_db, None, query="bowling")
    assert rows and rows[0].id == target.id


def test_electrician_via_google_primary(mem_db: Session) -> None:
    target = _provider(
        mem_db,
        "Volt Brothers",
        category="contractor",
        google_primary_category="electrician",
    )
    _provider(mem_db, "Aaa Bakery", category="bakery")
    rows = cb._fetch_provider_rows(mem_db, None, query="electrician")
    assert rows and rows[0].id == target.id


def test_leaf_routing_pulls_entity_categorized_provider(mem_db: Session) -> None:
    # Provider has NO matching text anywhere — only its entity's leaf membership.
    dept = Category(slug="home-prop", name="Home", sort_order=0, level=0)
    mem_db.add(dept)
    mem_db.flush()
    leaf = Category(slug="plumbing", name="Plumbing", sort_order=0, level=1, parent_id=dept.id)
    mem_db.add(leaf)
    mem_db.flush()
    ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}", name="Quiet Co")
    mem_db.add(ent)
    mem_db.flush()
    mem_db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    target = _provider(mem_db, "Quiet Co", category="x", entity_id=ent.id)
    rows = cb._fetch_provider_rows(mem_db, None, query="best plumber in town")
    assert any(r.id == target.id for r in rows)


def test_category_needle_outranks_incidental_token_match(mem_db: Session) -> None:
    incidental = _provider(
        mem_db,
        "Plumber Street Tacos",  # token 'plumber' in name only, verified
        category="restaurant",
        verified=True,
    )
    confirmed = _provider(
        mem_db,
        "Zz Pipeworks",
        category="services",
        google_primary_category="plumber",
        verified=False,
    )
    rows = cb._fetch_provider_rows(mem_db, None, query="i need a plumber")
    ids = [r.id for r in rows]
    assert ids.index(confirmed.id) < ids.index(incidental.id)


# --- degraded / legacy behavior preserved -------------------------------------


def test_no_token_query_keeps_verified_then_name_order(mem_db: Session) -> None:
    _provider(mem_db, "Beta Biz", verified=False)
    _provider(mem_db, "Alpha Biz", verified=True)
    _provider(mem_db, "Charlie Biz", verified=True)
    rows = cb._fetch_provider_rows(mem_db, None, query="")
    names = [r.provider_name for r in rows]
    assert names == ["Alpha Biz", "Charlie Biz", "Beta Biz"]


def test_entity_match_still_listed_first(mem_db: Session) -> None:
    _provider(mem_db, "Aaa Other", verified=True)
    target = _provider(mem_db, "Scooter's Place", verified=False)
    rows = cb._fetch_provider_rows(mem_db, "Scooter's Place", query="tell me about scooter's")
    assert rows and rows[0].id == target.id


def test_no_actives_returns_verified_fallback_slice(mem_db: Session) -> None:
    inactive_verified = Provider(
        provider_name="Ghost Verified",
        slug=f"p-{uuid4().hex[:10]}",
        category="x",
        draft=False,
        is_active=False,
        verified=True,
    )
    mem_db.add(inactive_verified)
    mem_db.flush()
    rows = cb._fetch_provider_rows(mem_db, None, query="anything")
    assert [r.provider_name for r in rows] == ["Ghost Verified"]


def test_cap_at_max_providers(mem_db: Session) -> None:
    for i in range(cb.MAX_PROVIDERS + 5):
        _provider(mem_db, f"Plumb Co {i:02d}", google_primary_category="plumber")
    rows = cb._fetch_provider_rows(mem_db, None, query="plumber")
    assert len(rows) == cb.MAX_PROVIDERS


# --- C-PR-4: spell-correct output reaches the Tier-3 scorer -------------------


def test_misspelled_category_reaches_tier3_candidates(mem_db: Session) -> None:
    target = _provider(
        mem_db, "All Seasons Co", category="home_services", google_primary_category="plumber"
    )
    _provider(mem_db, "Aaa Distractor", category="cafe")
    for query in ("plummbers", "i need a pluimber", "best plummbers in lake havasu"):
        rows = cb._fetch_provider_rows(mem_db, None, query=query)
        assert rows and rows[0].id == target.id, query


def test_spell_correct_does_not_touch_clean_queries(mem_db: Session) -> None:
    target = _provider(mem_db, "Volt Bros", google_primary_category="electrician")
    rows = cb._fetch_provider_rows(mem_db, None, query="electrician")
    assert rows and rows[0].id == target.id
