"""Tier 2 ranking bonuses + FTS base score (Phase 2B.2).

Search memo §4.4: ``ts_rank_cd`` scaled × 100 plus verification freshness and
featured. SQL helpers are Postgres-only; :func:`composite_rank_float` is pure
Python for unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, case, cast
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.search import fts as search_fts


@dataclass(frozen=True)
class Tier2RankInputs:
    """ORM-neutral inputs for :func:`composite_rank_float`."""

    fts_score: float
    last_verified_at: datetime | None
    featured: bool
    ref_now: datetime


def composite_rank_float(inp: Tier2RankInputs) -> float:
    """Pure ranking sum for unit tests (verification + featured + FTS base).

    Verification freshness: +30 within 30 days, +15 within 90 days, else 0.
    Featured: +25. ``fts_score`` is the pre-scaled ``ts_rank_cd * 100`` value.
    """
    score = float(inp.fts_score)
    if inp.featured:
        score += 25.0
    lv = inp.last_verified_at
    if lv is not None:
        if lv.tzinfo is None:
            lv = lv.replace(tzinfo=UTC)
        ref = inp.ref_now if inp.ref_now.tzinfo else inp.ref_now.replace(tzinfo=UTC)
        if lv > ref - timedelta(days=30):
            score += 30.0
        elif lv > ref - timedelta(days=90):
            score += 15.0
    return score


def _verification_bonus_sql(
    last_verified_col: InstrumentedAttribute[datetime | None],
    ref_now: datetime,
) -> ColumnElement[Any]:
    cut30 = ref_now - timedelta(days=30)
    cut90 = ref_now - timedelta(days=90)
    return cast(
        case(
            (last_verified_col > cut30, 30),
            (last_verified_col > cut90, 15),
            else_=0,
        ),
        Float,
    )


def fts_rank_scaled(tsquery_str: str) -> ColumnElement[Any]:
    """``ts_rank_cd(...) * 100`` as a typed SQL expression."""
    return cast(search_fts.fts_rank_cd_expr(tsquery_str), Float) * 100.0


def tier2_rank_score_sql(
    tsquery_str: str,
    *,
    last_verified_col: InstrumentedAttribute[datetime | None],
    featured_col: InstrumentedAttribute[bool],
    ref_now: datetime,
) -> ColumnElement[Any]:
    """Composite ORDER BY expression (FTS base + verification + featured)."""
    return (
        fts_rank_scaled(tsquery_str)
        + _verification_bonus_sql(last_verified_col, ref_now)
        + case((featured_col.is_(True), 25.0), else_=0.0)
    )


def build_rank_score_expr_for_filters(
    filters: Any,
    *,
    last_verified_col: InstrumentedAttribute[datetime | None],
    featured_col: InstrumentedAttribute[bool],
    ref_now: datetime,
) -> ColumnElement[Any] | None:
    """Return rank SQL when ``filters`` yield a non-empty tsquery; else None."""
    tsq = search_fts.build_tsquery_string(filters)
    if tsq is None:
        return None
    return tier2_rank_score_sql(
        tsq,
        last_verified_col=last_verified_col,
        featured_col=featured_col,
        ref_now=ref_now,
    )
