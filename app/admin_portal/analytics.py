"""Owner dashboards — traffic, search intelligence, placement performance.

Built directly on the first-party tables (``analytics_events``, ``query_log``,
``chat_logs``, ``placements``, ``revenue_events``) per plan §2.3 — NO PostHog /
second analytics platform. Plausible stays the client-side pageview tracker; it
exposes no server API here, so "traffic" is derived from first-party signals
(distinct chat sessions + ad-surface impression volume) and the dashboard says so.

Read-only. Every route is admin-guarded like the rest of the portal.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.admin_portal.guard import guard
from app.admin_portal.shared import render, window_start
from app.db.database import get_db
from app.db.models import AnalyticsEvent, ChatLog, Provider, QueryLog
from app.db.monetization_models import Placement, RevenueEvent

router = APIRouter()

# Rolling windows offered by the dashboards.
_WINDOWS: dict[str, int | None] = {"7d": 7, "30d": 30, "90d": 90, "all": None}
_DEFAULT_WINDOW = "30d"


def _window(value: str) -> tuple[str, datetime | None]:
    key = value if value in _WINDOWS else _DEFAULT_WINDOW
    days = _WINDOWS[key]
    return key, (window_start(days) if days is not None else None)


# --------------------------------------------------------------------------- #
# Traffic
# --------------------------------------------------------------------------- #


@router.get("/traffic", response_model=None)
def traffic(
    request: Request, window: str = _DEFAULT_WINDOW, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    win, since = _window(window)
    user_turns = ChatLog.role == "user"

    def _scoped(stmt, col):
        return stmt.where(col >= since) if since is not None else stmt

    sessions = int(
        db.execute(
            _scoped(
                select(func.count(func.distinct(ChatLog.session_id))).where(user_turns),
                ChatLog.created_at,
            )
        ).scalar()
        or 0
    )
    ask_turns = int(
        db.execute(
            _scoped(select(func.count()).where(user_turns), ChatLog.created_at)
        ).scalar()
        or 0
    )
    total_events = int(
        db.execute(
            _scoped(select(func.count()).select_from(AnalyticsEvent), AnalyticsEvent.created_at)
        ).scalar()
        or 0
    )

    surface = func.coalesce(AnalyticsEvent.slot_origin, AnalyticsEvent.slot, "(home)")
    top_surfaces = db.execute(
        _scoped(
            select(surface.label("surface"), func.count().label("n")),
            AnalyticsEvent.created_at,
        )
        .group_by(surface)
        .order_by(desc("n"))
        .limit(20)
    ).all()

    top_categories = db.execute(
        _scoped(
            select(QueryLog.category, func.count().label("n")).where(
                QueryLog.category.is_not(None)
            ),
            QueryLog.created_at,
        )
        .group_by(QueryLog.category)
        .order_by(desc("n"))
        .limit(20)
    ).all()

    return render(
        request,
        "portal_traffic.html",
        "traffic",
        {
            "window": win,
            "windows": list(_WINDOWS),
            "sessions": sessions,
            "ask_turns": ask_turns,
            "total_events": total_events,
            "top_surfaces": [(s, n) for s, n in top_surfaces],
            "top_categories": [(c, n) for c, n in top_categories],
        },
    )


# --------------------------------------------------------------------------- #
# Search intelligence
# --------------------------------------------------------------------------- #


@router.get("/search", response_model=None)
def search(
    request: Request, window: str = _DEFAULT_WINDOW, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    win, since = _window(window)

    def _scoped(stmt):
        return stmt.where(QueryLog.created_at >= since) if since is not None else stmt

    zero = func.sum(case((QueryLog.result_count == 0, 1), else_=0))
    top_queries = db.execute(
        _scoped(
            select(
                QueryLog.normalized_intent,
                func.count().label("n"),
                func.avg(QueryLog.result_count).label("avg_results"),
                zero.label("zero_results"),
            )
        )
        .group_by(QueryLog.normalized_intent)
        .order_by(desc("n"))
        .limit(40)
    ).all()

    zero_result_queries = db.execute(
        _scoped(
            select(QueryLog.normalized_intent, func.count().label("n")).where(
                QueryLog.result_count == 0
            )
        )
        .group_by(QueryLog.normalized_intent)
        .order_by(desc("n"))
        .limit(25)
    ).all()

    # query -> category flow: the category each search resolved into (the durable,
    # anonymized signal QueryLog already captures). Listing-grain click flows need
    # a session join key the schema doesn't carry yet (see dashboard note).
    category_flow = db.execute(
        _scoped(
            select(QueryLog.category, func.count().label("n")).where(
                QueryLog.category.is_not(None)
            )
        )
        .group_by(QueryLog.category)
        .order_by(desc("n"))
        .limit(25)
    ).all()

    layer_mix = db.execute(
        _scoped(
            select(QueryLog.min_layer, func.count().label("n")).where(
                QueryLog.min_layer.is_not(None)
            )
        )
        .group_by(QueryLog.min_layer)
        .order_by(desc("n"))
    ).all()

    total_queries = int(
        db.execute(_scoped(select(func.count()).select_from(QueryLog))).scalar() or 0
    )

    return render(
        request,
        "portal_search.html",
        "search",
        {
            "window": win,
            "windows": list(_WINDOWS),
            "total_queries": total_queries,
            "top_queries": [
                (q, n, round(float(avg or 0), 1), int(z or 0))
                for q, n, avg, z in top_queries
            ],
            "zero_result_queries": [(q, n) for q, n in zero_result_queries],
            "category_flow": [(c, n) for c, n in category_flow],
            "layer_mix": [(layer, n) for layer, n in layer_mix],
        },
    )


# --------------------------------------------------------------------------- #
# Placement performance
# --------------------------------------------------------------------------- #


@router.get("/placements", response_model=None)
def placements(
    request: Request, window: str = _DEFAULT_WINDOW, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    win, since = _window(window)

    # event_name follows the "<surface>.<slot>.impression" / ".click" suffix
    # convention, so anchor to the suffix (precise; won't miscount a future
    # "impression_count"-style name). The slot group-by below rides the
    # ix_analytics_events_slot_created index (P6 M1).
    imp = func.sum(case((AnalyticsEvent.event_name.like("%.impression"), 1), else_=0))
    clk = func.sum(case((AnalyticsEvent.event_name.like("%.click"), 1), else_=0))

    def _scoped_ae(stmt):
        return stmt.where(AnalyticsEvent.created_at >= since) if since is not None else stmt

    by_slot = db.execute(
        _scoped_ae(
            select(
                func.coalesce(AnalyticsEvent.slot, "(none)").label("slot"),
                imp.label("imp"),
                clk.label("clk"),
            )
        )
        .group_by(AnalyticsEvent.slot)
        .order_by(desc("imp"))
    ).all()

    slot_rows = []
    for slot, i, c in by_slot:
        i_n, c_n = int(i or 0), int(c or 0)
        ctr = f"{(c_n / i_n * 100):.1f}%" if i_n else "—"
        slot_rows.append({"slot": slot, "impressions": i_n, "clicks": c_n, "ctr": ctr})

    # Revenue ledger summary by kind (over the window).
    def _scoped_rev(stmt):
        return stmt.where(RevenueEvent.created_at >= since) if since is not None else stmt

    rev_by_kind = db.execute(
        _scoped_rev(
            select(
                RevenueEvent.kind,
                func.count().label("n"),
                func.coalesce(func.sum(RevenueEvent.amount_cents), 0).label("cents"),
            )
        ).group_by(RevenueEvent.kind)
    ).all()
    revenue = [
        {"kind": k, "n": int(n or 0), "dollars": f"{(int(cents or 0) / 100):.2f}"}
        for k, n, cents in rev_by_kind
    ]

    # Current placement roster with status.
    status_counts = db.execute(
        select(Placement.status, func.count()).group_by(Placement.status)
    ).all()
    roster = db.execute(
        select(Placement, Provider.provider_name)
        .join(Provider, Provider.id == Placement.provider_id, isouter=True)
        .order_by(desc(Placement.created_at))
        .limit(50)
    ).all()
    roster_rows = [
        {
            "provider": name or p.provider_id,
            "type": p.placement_type,
            "where": p.category_slug or "Homepage",
            "status": p.status,
            "price": f"${p.price_cents / 100:.0f}" if p.price_cents else "—",
            "paid_through": p.paid_through,
        }
        for p, name in roster
    ]

    return render(
        request,
        "portal_placements.html",
        "placements",
        {
            "window": win,
            "windows": list(_WINDOWS),
            "slot_rows": slot_rows,
            "revenue": revenue,
            "status_counts": {str(s): int(n) for s, n in status_counts},
            "roster_rows": roster_rows,
        },
    )
