"""Unit tests for ``app.search.fts`` tsquery builders (Phase 2B.2)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.chat.tier2_schema import Tier2Filters
from app.search import fts as search_fts


def _f(**kwargs: object) -> Tier2Filters:
    base: dict[str, object] = {"parser_confidence": 0.9, "fallback_to_tier3": False}
    base.update(kwargs)
    return Tier2Filters(**base)  # type: ignore[arg-type]


def test_build_tsquery_entity_name_two_tokens() -> None:
    q = search_fts.build_tsquery_entity_name_only(_f(entity_name="plumber repair"))
    assert q == "(plumber & repair)"


def test_build_tsquery_entity_name_strips_unsafe_tokens() -> None:
    assert (
        search_fts.build_tsquery_entity_name_only(_f(entity_name="plumber's OR 1=1"))
        is None
    )


def test_build_tsquery_string_combines_name_and_category_synonyms() -> None:
    s = search_fts.build_tsquery_string(_f(entity_name="plumber repair", category="barbershop"))
    assert s is not None
    assert "(plumber & repair)" in s
    assert "barber" in s


def test_build_tsquery_string_category_barbershop_has_or_group() -> None:
    s = search_fts.build_tsquery_string(_f(category="barbershop"))
    assert s is not None
    assert "|" in s


def test_build_tsquery_string_empty_when_no_text_filters() -> None:
    assert search_fts.build_tsquery_string(_f()) is None


def test_has_rankable_tsquery() -> None:
    assert search_fts.has_rankable_tsquery(_f(entity_name="x")) is True
    assert search_fts.has_rankable_tsquery(_f()) is False


def test_phrase_to_tsquery_group_multiword() -> None:
    assert search_fts._phrase_to_tsquery_group("coffee shop") == "(coffee & shop)"


def test_category_synonyms_tsquery_or_group_non_empty() -> None:
    g = search_fts._category_synonyms_tsquery_or_group("coffee shops")
    assert g is not None
    assert "|" in g


@pytest.mark.skipif(
    not str(os.environ.get("DATABASE_URL", "")).startswith("postgresql"),
    reason="Postgres-only: entities.search_vector",
)
def test_build_entity_select_postgres_compiles() -> None:
    eng = create_engine(os.environ["DATABASE_URL"])
    with Session(eng) as session:
        stmt = search_fts.build_entity_select_for_filters(
            session, _f(entity_name="test"), entity_type="commercial", limit=4
        )
        session.get_bind().execute(stmt.limit(0))


@pytest.mark.skipif(
    str(os.environ.get("DATABASE_URL", "")).startswith("postgresql"),
    reason="SQLite path: compile-only without Postgres bind",
)
def test_build_entity_select_sqlite_returns_selectable() -> None:
    from sqlalchemy.dialects import sqlite as sqlite_d

    eng = create_engine("sqlite:///:memory:")
    with Session(eng) as session:
        stmt = search_fts.build_entity_select_for_filters(session, _f(entity_name="a"))
        stmt.compile(dialect=sqlite_d.dialect())
