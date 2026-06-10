"""Chat insights — rollups over ChatLog the existing analytics page lacks.

Volume, tier/cache breakdowns, latency, token usage with estimated cost,
feedback signals, and a sample of recent unmatched user queries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import Date, cast, desc, func, select
from sqlalchemy.orm import Session

from app.admin_portal.guard import guard
from app.admin_portal.shared import render, window_start
from app.db.database import get_db
from app.db.models import ChatLog

router = APIRouter()

# Display-only cost estimate, priced for the production Tier-3 model:
# gpt-4.1-mini (the code default in app/chat/tier3_handler.py — the TIER3_MODEL
# env var exists only as an emergency-rollback override). Published OpenAI
# rates per 1M tokens (USD): $0.40 input / $1.60 output. Adjust here when the
# production model/pricing changes.
INPUT_COST_PER_M = 0.40
OUTPUT_COST_PER_M = 1.60

_WINDOWS = (7, 30, 90)


def _breakdown(db: Session, column, since) -> list[tuple[str, int]]:
    rows = db.execute(
        select(func.coalesce(column, "(none)"), func.count())
        .select_from(ChatLog)
        .where(ChatLog.role == "user", ChatLog.created_at >= since)
        .group_by(column)
        .order_by(desc(func.count()))
    ).all()
    return [(str(k), int(n)) for k, n in rows]


@router.get("/chat", response_model=None)
def chat_insights(
    request: Request, days: int = 7, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    if days not in _WINDOWS:
        days = 7
    since = window_start(days)

    user_turns = ChatLog.role == "user"
    in_window = ChatLog.created_at >= since

    daily = db.execute(
        select(cast(ChatLog.created_at, Date).label("d"), func.count())
        .where(user_turns, in_window)
        .group_by("d")
        .order_by("d")
    ).all()
    max_daily = max((n for _, n in daily), default=0)

    totals = db.execute(
        select(
            func.count(),
            func.count(func.distinct(ChatLog.session_id)),
            func.avg(ChatLog.latency_ms),
            func.coalesce(func.sum(ChatLog.llm_input_tokens), 0),
            func.coalesce(func.sum(ChatLog.llm_output_tokens), 0),
        ).where(user_turns, in_window)
    ).one()
    messages, sessions, avg_latency, tok_in, tok_out = totals
    est_cost = (tok_in / 1e6) * INPUT_COST_PER_M + (tok_out / 1e6) * OUTPUT_COST_PER_M

    cache_rows = _breakdown(db, ChatLog.cache_status, since)
    cache_total = sum(n for _, n in cache_rows)
    cache_hits = sum(n for k, n in cache_rows if k.startswith("hit"))
    cache_hit_pct = round(100 * cache_hits / cache_total, 1) if cache_total else None

    unmatched = db.execute(
        select(ChatLog)
        .where(user_turns, in_window, ChatLog.tier_used.is_(None))
        .order_by(desc(ChatLog.created_at))
        .limit(25)
    ).scalars().all()

    slowest = db.execute(
        select(ChatLog)
        .where(user_turns, in_window, ChatLog.latency_ms.isnot(None))
        .order_by(desc(ChatLog.latency_ms))
        .limit(10)
    ).scalars().all()

    return render(
        request,
        "portal_chat.html",
        "chat",
        {
            "days": days,
            "windows": _WINDOWS,
            "daily": daily,
            "max_daily": max_daily,
            "messages": int(messages or 0),
            "sessions": int(sessions or 0),
            "avg_latency": round(avg_latency) if avg_latency is not None else None,
            "tok_in": int(tok_in),
            "tok_out": int(tok_out),
            "est_cost": round(est_cost, 2),
            "tiers": _breakdown(db, ChatLog.tier_used, since),
            "cache": cache_rows,
            "cache_hit_pct": cache_hit_pct,
            "intents": _breakdown(db, ChatLog.intent, since)[:15],
            "feedback": _breakdown(db, ChatLog.feedback_signal, since),
            "unmatched": unmatched,
            "slowest": slowest,
        },
    )
