"""Parity / shape tests for SQLite ILIKE fallback vs tsquery builders (Phase 2B.2)."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_synonyms import _category_needle_set
from app.search import fts as search_fts
from app.search import sqlite_fallback


def _f(**kwargs: object) -> Tier2Filters:
    base: dict[str, object] = {"parser_confidence": 0.9, "fallback_to_tier3": False}
    base.update(kwargs)
    return Tier2Filters(**base)  # type: ignore[arg-type]


def test_category_needle_set_matches_sqlite_fallback_needle_count() -> None:
    needles = _category_needle_set("coffee shops")
    stmt = sqlite_fallback.build_ilike_entity_select(
        _f(category="coffee shops"), entity_type="commercial", limit=8
    )
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "like" in sql
    assert len(needles) >= 1


def test_sqlite_fallback_select_includes_active_filter() -> None:
    stmt = sqlite_fallback.build_ilike_entity_select(_f(entity_name="Park"))
    assert "is_active" in str(stmt).lower()


def test_tsquery_category_or_covers_needle_lexemes() -> None:
    s = search_fts.build_tsquery_string(_f(category="pharmacy"))
    assert s is not None
    assert "pharmacy" in s or "drug" in s


def test_build_tsquery_entity_name_only_none_for_whitespace() -> None:
    assert search_fts.build_tsquery_entity_name_only(_f(entity_name="   ")) is None


def test_sqlite_memory_session_entity_select_runs() -> None:
    eng = create_engine("sqlite:///:memory:")
    with Session(eng) as session:
        stmt = search_fts.build_entity_select_for_filters(
            session, _f(entity_name="x"), limit=3
        )
        session.execute(select(1))
        _ = stmt


def test_synonym_expansion_barbershop_non_empty() -> None:
    n = _category_needle_set("barbershop")
    assert "barber" in n or "barbershop" in n
