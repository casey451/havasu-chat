"""Postgres FTS query helpers for Tier 2 (Phase 2B.2).

Pure builders over SQLAlchemy expressions; callers supply the bound
:class:`~sqlalchemy.orm.Session` for dialect checks only.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.sql import expression as sql_exp
from sqlalchemy.sql.elements import ColumnElement

from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_synonyms import _category_needle_set

# English lexeme tokens for to_tsquery (no quotes / operators in output).
_TOKEN_RE = re.compile(r"^[a-z0-9]+$")
_TSQUERY_RESERVED = frozenset({"or", "and", "not"})


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _phrase_to_tsquery_group(phrase: str) -> str | None:
    """Turn a free-text phrase into a ``(tok1 & tok2 & ...)`` tsquery group."""
    toks = [
        t.lower()
        for t in phrase.replace("'", " ").split()
        if t and _TOKEN_RE.match(t.lower()) and t.lower() not in _TSQUERY_RESERVED
    ]
    if not toks:
        return None
    return "(" + " & ".join(toks) + ")"


def _category_synonyms_tsquery_or_group(cat: str) -> str | None:
    """OR needles from :func:`app.chat.tier2_synonyms._category_needle_set` as tsquery."""
    needles = _category_needle_set(cat)
    groups: list[str] = []
    for n in needles:
        g = _phrase_to_tsquery_group(n)
        if g:
            groups.append(g)
    if not groups:
        return None
    return "(" + " | ".join(groups) + ")"


def build_tsquery_string(filters: Tier2Filters) -> str | None:
    """Compose a ``to_tsquery('english', ...)`` string from Tier 2 text filters.

    AND across dimensions (entity name tokens AND category synonym group),
    OR within synonym needles — mirrors the LIKE-chain semantics in
    ``tier2_db_query`` (Phase 2B.2 brief §6.3).
    """
    parts: list[str] = []
    if filters.entity_name and filters.entity_name.strip():
        tokens = [t for t in filters.entity_name.strip().split() if t]
        if tokens:
            safe_toks = [
                t.lower()
                for t in tokens
                if _TOKEN_RE.match(t.lower()) and t.lower() not in _TSQUERY_RESERVED
            ]
            if safe_toks:
                parts.append("(" + " & ".join(safe_toks) + ")")
    if filters.category and filters.category.strip():
        cat_grp = _category_synonyms_tsquery_or_group(filters.category)
        if cat_grp:
            parts.append(cat_grp)
    if not parts:
        return None
    return " & ".join(parts)


def build_tsquery_entity_name_only(filters: Tier2Filters) -> str | None:
    """Tsquery string from ``entity_name`` only (WHERE name-dimension)."""
    if not (filters.entity_name and filters.entity_name.strip()):
        return None
    tokens = [t for t in filters.entity_name.strip().split() if t]
    safe_toks = [
        t.lower()
        for t in tokens
        if _TOKEN_RE.match(t.lower()) and t.lower() not in _TSQUERY_RESERVED
    ]
    if not safe_toks:
        return None
    return "(" + " & ".join(safe_toks) + ")"


def entities_search_vector_match(tsquery_str: str) -> ColumnElement[bool]:
    """``entities.search_vector @@ to_tsquery('english', <tsquery_str>)`` (Postgres)."""
    return sql_exp.text("entities.search_vector @@ to_tsquery('english', :__tier2_tsq)").bindparams(
        __tier2_tsq=tsquery_str
    )


def fts_rank_cd_expr(tsquery_str: str) -> Any:
    """``ts_rank_cd(entities.search_vector, to_tsquery('english', ...))`` as SQL expr."""
    return sql_exp.text(
        "COALESCE(ts_rank_cd(entities.search_vector, "
        "to_tsquery('english', :__tier2_tsq_rank)), 0.0)"
    ).bindparams(__tier2_tsq_rank=tsquery_str)


def has_rankable_tsquery(filters: Tier2Filters) -> bool:
    return build_tsquery_string(filters) is not None


# --- Optional Select builder (search bar / future callers) -----------------


def build_entity_select_for_filters(
    session: Session,
    filters: Tier2Filters,
    *,
    entity_type: str | None = None,
    limit: int = 8,
) -> Any:
    """Return a SQLAlchemy select of Entity rows matching text filters.

    Postgres: ``search_vector @@ to_tsquery``. SQLite: ILIKE on name/description
    via :mod:`app.search.sqlite_fallback`.
    """
    from sqlalchemy import select

    from app.db.models import Entity
    from app.search import sqlite_fallback

    if _is_postgres(session):
        tsq = build_tsquery_string(filters)
        q = select(Entity).where(Entity.is_active.is_(True))
        if entity_type:
            q = q.where(Entity.entity_type == entity_type)
        if tsq:
            q = q.where(entities_search_vector_match(tsq))
        return q.limit(limit)
    return sqlite_fallback.build_ilike_entity_select(filters, entity_type=entity_type, limit=limit)
