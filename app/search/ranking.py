"""Tier 2 ranking bonuses + FTS base score (Phase 2B.2).

Search memo §4.4: ``ts_rank_cd`` scaled × 100 plus verification freshness and
featured. SQL helpers are Postgres-only; :func:`composite_rank_float` is pure
Python for unit tests.

Ranking v2 (2026-07-08 re-audit item 6) adds a category-assignment match bonus
and a bounded review-count lift, gated behind ``SEARCH_RANKING_V2`` so the live
result order is unchanged until Casey flips it (see :func:`search_ranking_v2_enabled`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, case, cast, func
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.core.liveness import (
    DAMPENER_FLOOR,
    MAX_COUNT,
    liveness_dampener,
    popularity_component,
)
from app.search import fts as search_fts


def search_ranking_v2_enabled() -> bool:
    """True when the ranking-v2 signals (category-assignment match + review-count
    lift) are wired into the SQL ORDER BY. Off by default so prod result order is
    unchanged until Casey opts in via ``SEARCH_RANKING_V2=1`` (read per-call so a
    flip doesn't need a redeploy)."""
    return (os.getenv("SEARCH_RANKING_V2") or "").strip().lower() in {"1", "true", "yes", "on"}


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
    # Ranking v2 (2026-07-08 re-audit item 6): the query's resolved category/leaf
    # matches the entity's ASSIGNED primary category (EntityCategory), not just
    # description text; and the listing's Google review count. Both default to the
    # v1 no-op so existing callers are unchanged until the route opts in.
    category_match: bool = False
    review_count: int | None = None


#: Field-identity bonus: a NAME match must outrank a description/amenity-only
#: match no matter what freshness (+30) and featured (+25) bonuses the other
#: row carries — 60 > 30 + 25. Live failure this fixes: "pool service" ranked
#: hotels-with-pools and billiards halls (both fresh-verified, "pool" only in
#: the description) beside the actual pool companies.
NAME_MATCH_BONUS = 60.0

# ── Ranking v2 tunables (2026-07-08 re-audit item 6) ──────────────────────────
# Field-identity ladder: NAME (60) > CATEGORY (35) > description/FTS-only (0).
# CATEGORY_MATCH_BONUS sits below NAME so an exact name always outranks a
# tag/category-only match at equal other bonuses; it sits above freshness (30) so
# a provider actually filed under the queried leaf beats one that merely mentions
# the word. REVIEW_BONUS_MAX is the max review lift (at the busiest listing) and
# is deliberately SMALL — below the NAME↔CATEGORY gap (25) and below freshness —
# so review count only breaks ties among similarly-relevant results and a
# high-review but weakly-relevant listing can never leapfrog a name/category match.
CATEGORY_MATCH_BONUS = 35.0
REVIEW_BONUS_MAX = 12.0


def review_count_bonus(review_count: int | None) -> float:
    """Bounded, log-scaled review lift in ``[0, REVIEW_BONUS_MAX]``.

    ``REVIEW_BONUS_MAX * min(1, popularity_component(review_count))`` — the same
    log-normalised popularity curve the liveness score uses, so a 500-review shop
    edges out a 5-review one without a 10,000-review outlier running away. Clamped
    at 1 (mirrors the SQL ``least(norm, 1.0)``) so a listing busier than the
    calibration max can't exceed the cap. NULL/0 reviews → 0 (the v1 no-op)."""
    return REVIEW_BONUS_MAX * min(1.0, popularity_component(review_count))


def composite_rank_float(inp: Tier2RankInputs) -> float:
    """Pure ranking sum for unit tests (verification + featured + FTS base).

    Verification freshness: +30 within 30 days, +15 within 90 days, else 0.
    Featured: +25. Name match: +NAME_MATCH_BONUS (dominates the other bonuses,
    so field identity orders first and freshness orders within it). Category
    match: +CATEGORY_MATCH_BONUS (below name). Review count: a bounded log lift
    (:func:`review_count_bonus`) that only breaks ties. ``fts_score`` is the
    pre-scaled ``ts_rank_cd * 100`` value. The composite is then scaled by the
    liveness dampener (NULL → unchanged).
    """
    score = float(inp.fts_score)
    if inp.name_match:
        score += NAME_MATCH_BONUS
    if inp.category_match:
        score += CATEGORY_MATCH_BONUS
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
    score += review_count_bonus(inp.review_count)
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


def category_match_bonus_sql(match_cond: ColumnElement[Any]) -> ColumnElement[Any]:
    """+CATEGORY_MATCH_BONUS when ``match_cond`` is true (the entity is FILED under
    the query's resolved leaf, not merely text-matching the word). Ranking v2."""
    return cast(case((match_cond, CATEGORY_MATCH_BONUS), else_=0.0), Float)


def review_count_bonus_sql(review_count_col: ColumnElement[Any]) -> ColumnElement[Any]:
    """Bounded log-scaled review lift, mirroring :func:`review_count_bonus`:
    ``REVIEW_BONUS_MAX * LEAST(ln(1 + coalesce(count, 0)) / ln(1 + MAX_COUNT), 1.0)``.
    NULL/0 reviews → 0. Ranking v2."""
    norm = func.ln(1.0 + func.coalesce(cast(review_count_col, Float), 0.0)) / func.ln(
        1.0 + float(MAX_COUNT)
    )
    return cast(REVIEW_BONUS_MAX * func.least(norm, 1.0), Float)


def tier2_rank_score_sql(
    tsquery_str: str,
    *,
    last_verified_col: InstrumentedAttribute[datetime | None],
    featured_col: InstrumentedAttribute[bool],
    ref_now: datetime,
    liveness_col: ColumnElement[Any] | None = None,
    category_match_cond: ColumnElement[Any] | None = None,
    review_count_col: ColumnElement[Any] | None = None,
) -> ColumnElement[Any]:
    """Composite ORDER BY expression (FTS base + verification + featured).

    When ``liveness_col`` is provided, the composite is scaled by the stored
    liveness dampener so stale listings sink without being excluded. When
    ``category_match_cond`` / ``review_count_col`` are provided (ranking v2), the
    assigned-category bonus and the bounded review lift are added to the base.
    """
    composite = (
        fts_rank_scaled(tsquery_str)
        + name_match_bonus_sql(tsquery_str)
        + _verification_bonus_sql(last_verified_col, ref_now)
        + case((featured_col.is_(True), 25.0), else_=0.0)
    )
    if category_match_cond is not None:
        composite = composite + category_match_bonus_sql(category_match_cond)
    if review_count_col is not None:
        composite = composite + review_count_bonus_sql(review_count_col)
    damp = liveness_dampener_sql(liveness_col)
    return composite if damp is None else composite * damp


def build_rank_score_expr_for_filters(
    filters: Any,
    *,
    last_verified_col: InstrumentedAttribute[datetime | None],
    featured_col: InstrumentedAttribute[bool],
    ref_now: datetime,
    liveness_col: ColumnElement[Any] | None = None,
    category_match_cond: ColumnElement[Any] | None = None,
    review_count_col: ColumnElement[Any] | None = None,
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
        category_match_cond=category_match_cond,
        review_count_col=review_count_col,
    )
