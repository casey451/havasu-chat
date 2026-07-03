"""Tier 2 ranking bonuses + FTS base score (Phase 2B.2).

Search memo §4.4: ``ts_rank_cd`` scaled × 100 plus verification freshness and
featured. SQL helpers are Postgres-only; :func:`composite_rank_float` is pure
Python for unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, case, cast, func
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.core.liveness import DAMPENER_FLOOR, liveness_dampener
from app.search import fts as search_fts


@dataclass(frozen=True)
class Tier2RankInputs:
    """ORM-neutral inputs for :func:`composite_rank_float`."""

    fts_score: float
    last_verified_at: datetime | None
    featured: bool
    ref_now: datetime
    # Liveness dampener input (0–1). ``None`` → no dampening. See app/core/liveness.py.
    liveness_score: float | None = None
    # 2026-07-01 (master audit §4.6): the query matched the entity NAME itself,
    # not just description/amenity text.
    name_match: bool = False


#: Field-identity bonus: a NAME match must outrank a description/amenity-only
#: match no matter what freshness (+30) and featured (+25) bonuses the other
#: row carries — 60 > 30 + 25. Live failure this fixes: "pool service" ranked
#: hotels-with-pools and billiards halls (both fresh-verified, "pool" only in
#: the description) beside the actual pool companies.
NAME_MATCH_BONUS = 60.0


def composite_rank_float(inp: Tier2RankInputs) -> float:
    """Pure ranking sum for unit tests (verification + featured + FTS base).

    Verification freshness: +30 within 30 days, +15 within 90 days, else 0.
    Featured: +25. Name match: +NAME_MATCH_BONUS (dominates the other bonuses,
    so field identity orders first and freshness orders within it).
    ``fts_score`` is the pre-scaled ``ts_rank_cd * 100`` value. The composite
    is then scaled by the liveness dampener (NULL → unchanged).
    """
    score = float(inp.fts_score)
    if inp.name_match:
        score += NAME_MATCH_BONUS
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
    return score * liveness_dampener(inp.liveness_score)


def liveness_dampener_sql(liveness_col: ColumnElement[Any] | None) -> ColumnElement[Any] | None:
    """SQL multiplier ``FLOOR + (1 - FLOOR) * COALESCE(liveness, 1.0)``.

    Mirrors :func:`app.core.liveness.liveness_dampener`: a NULL stored score
    coalesces to 1.0 (no dampening). Returns ``None`` when ``liveness_col`` is
    ``None`` so callers can skip the multiply entirely. Uses the *stored* score
    column directly — no exp/sqrt in SQL.
    """
    if liveness_col is None:
        return None
    return DAMPENER_FLOOR + (1.0 - DAMPENER_FLOOR) * func.coalesce(liveness_col, 1.0)


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


def name_match_bonus_sql(tsquery_str: str) -> ColumnElement[Any]:
    """+NAME_MATCH_BONUS when the entity NAME itself matches the tsquery.

    Postgres-only (like the rest of this module's SQL). The search_vector is
    name(A)+description(B), so ts_rank alone can't tell "matched the name"
    from "matched the description a lot" once the freshness/featured bonuses
    stack — this CASE restores field identity as the primary ordering.
    """
    from sqlalchemy.sql import expression as sql_exp

    cond = sql_exp.text(
        "to_tsvector('english', coalesce(entities.name, '')) @@ "
        "to_tsquery('english', :__tier2_tsq_nm)"
    ).bindparams(__tier2_tsq_nm=tsquery_str)
    return cast(case((cond, NAME_MATCH_BONUS), else_=0.0), Float)


def tier2_rank_score_sql(
    tsquery_str: str,
    *,
    last_verified_col: InstrumentedAttribute[datetime | None],
    featured_col: InstrumentedAttribute[bool],
    ref_now: datetime,
    liveness_col: ColumnElement[Any] | None = None,
) -> ColumnElement[Any]:
    """Composite ORDER BY expression (FTS base + verification + featured).

    When ``liveness_col`` is provided, the composite is scaled by the stored
    liveness dampener so stale listings sink without being excluded.
    """
    composite = (
        fts_rank_scaled(tsquery_str)
        + name_match_bonus_sql(tsquery_str)
        + _verification_bonus_sql(last_verified_col, ref_now)
        + case((featured_col.is_(True), 25.0), else_=0.0)
    )
    damp = liveness_dampener_sql(liveness_col)
    return composite if damp is None else composite * damp


def build_rank_score_expr_for_filters(
    filters: Any,
    *,
    last_verified_col: InstrumentedAttribute[datetime | None],
    featured_col: InstrumentedAttribute[bool],
    ref_now: datetime,
    liveness_col: ColumnElement[Any] | None = None,
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
        liveness_col=liveness_col,
    )
