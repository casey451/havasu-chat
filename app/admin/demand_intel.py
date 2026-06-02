"""Phase B8 — demand-intelligence dashboard (admin, READ-ONLY).

A read-only analytics surface over the ``query_log`` table
(:class:`app.db.models.QueryLog`). Three signals:

1. **Top intents** — ``group by normalized_intent`` with counts.
2. **Coverage gaps** — zero-result queries (``result_count == 0``) ranked by
   frequency. This is the demand-with-no-supply signal: people are asking and
   the catalog has nothing.
3. **Trends over time** — per-day query volume and per-day zero-result rate.

Everything here issues SELECT/aggregate queries only — NEVER a write. The
per-day trend is bucketed in Python (from ``created_at`` + ``result_count``)
rather than with a dialect-specific date function so the same code runs on
SQLite (tests) and Postgres (prod).

Mirrors the admin pattern in :mod:`app.admin.v1_overview`: a router, a
``_guard(request)`` cookie check, and a Jinja2 ``TemplateResponse``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.db.database import get_db
from app.db.models import QueryLog

router = APIRouter(prefix="/admin", tags=["admin"])

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))

# Default analysis windows. Top-intents / coverage-gaps use the wider window;
# the per-day trend uses the tighter one so the chart stays legible.
_GAP_WINDOW_DAYS = 30
_TREND_WINDOW_DAYS = 14
_TOP_LIMIT = 25


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def top_intents(db: Session, *, since: datetime, limit: int = _TOP_LIMIT) -> list[dict]:
    """Most-asked intents in the window: ``group by normalized_intent``.

    Returns rows ``{intent, total, zero_results}`` sorted by total desc. The
    ``zero_results`` column is the count of those turns that returned nothing,
    so a high-volume intent that is also mostly empty stands out.
    """
    rows = db.execute(
        select(QueryLog.normalized_intent, func.count().label("total"))
        .where(QueryLog.created_at >= since)
        .group_by(QueryLog.normalized_intent)
        .order_by(func.count().desc(), QueryLog.normalized_intent.asc())
        .limit(limit)
    ).all()
    # Zero-result count per intent, computed as its own unambiguous aggregate.
    zero_by_intent = dict(
        db.execute(
            select(QueryLog.normalized_intent, func.count())
            .where(QueryLog.created_at >= since, QueryLog.result_count == 0)
            .group_by(QueryLog.normalized_intent)
        ).all()
    )
    out: list[dict] = []
    for intent, total in rows:
        out.append(
            {
                "intent": intent,
                "total": int(total or 0),
                "zero_results": int(zero_by_intent.get(intent, 0)),
            }
        )
    return out


def coverage_gaps(db: Session, *, since: datetime, limit: int = _TOP_LIMIT) -> list[dict]:
    """Zero-result queries ranked by frequency — demand with no supply.

    Grouped by ``(normalized_intent, category)`` so a gap is attributable to a
    specific category bucket where possible.
    """
    rows = db.execute(
        select(
            QueryLog.normalized_intent,
            QueryLog.category,
            func.count().label("misses"),
        )
        .where(QueryLog.created_at >= since, QueryLog.result_count == 0)
        .group_by(QueryLog.normalized_intent, QueryLog.category)
        .order_by(func.count().desc(), QueryLog.normalized_intent.asc())
        .limit(limit)
    ).all()
    return [
        {"intent": intent, "category": category, "misses": int(misses or 0)}
        for intent, category, misses in rows
    ]


def daily_trends(db: Session, *, since: datetime) -> list[dict]:
    """Per-day query volume and zero-result rate, oldest day first.

    Bucketed in Python (no dialect-specific date function) so SQLite and
    Postgres behave identically. Days with no traffic are omitted (the table is
    sparse by nature; absence reads as zero).
    """
    rows = db.execute(
        select(QueryLog.created_at, QueryLog.result_count).where(QueryLog.created_at >= since)
    ).all()
    totals: dict[date, int] = defaultdict(int)
    zeros: dict[date, int] = defaultdict(int)
    for created_at, result_count in rows:
        if created_at is None:
            continue
        day = created_at.date()
        totals[day] += 1
        if (result_count or 0) == 0:
            zeros[day] += 1
    out: list[dict] = []
    for day in sorted(totals):
        total = totals[day]
        zero = zeros.get(day, 0)
        out.append(
            {
                "day": day.isoformat(),
                "total": total,
                "zero": zero,
                "zero_rate": round(zero / total, 3) if total else 0.0,
            }
        )
    return out


@router.get("/demand-intel", response_class=HTMLResponse)
def admin_demand_intel(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    redir = _guard(request)
    if redir:
        return redir

    now = _naive_utc_now()
    gap_since = now - timedelta(days=_GAP_WINDOW_DAYS)
    trend_since = now - timedelta(days=_TREND_WINDOW_DAYS)

    total_queries = int(
        db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.created_at >= gap_since))
        or 0
    )
    total_zero = int(
        db.scalar(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.created_at >= gap_since, QueryLog.result_count == 0)
        )
        or 0
    )
    zero_rate = round(total_zero / total_queries, 3) if total_queries else 0.0

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="admin_demand_intel.html",
        context={
            "gap_window_days": _GAP_WINDOW_DAYS,
            "trend_window_days": _TREND_WINDOW_DAYS,
            "total_queries": total_queries,
            "total_zero": total_zero,
            "zero_rate": zero_rate,
            "top": top_intents(db, since=gap_since),
            "gaps": coverage_gaps(db, since=gap_since),
            "trends": daily_trends(db, since=trend_since),
        },
    )
