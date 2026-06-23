"""Portal router — aggregates all portal pages under /admin/portal.

NOT registered anywhere. Activation is a deliberate two-line change in
app/main.py (see README.md in this directory). Prefix chosen to avoid
any collision with the existing /admin routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin_portal import (
    address_quality,
    analytics,
    audit_models,
    chat_insights,
    feedback,
    ops,
    users,
)
from app.admin_portal.audit_models import AdminAuditLog, audit_enabled
from app.admin_portal.guard import guard
from app.admin_portal.queues import queue_cards
from app.admin_portal.shared import render, window_start
from app.db.database import get_db
from app.db.models import ChatLog, Job, Outbox, User

portal_router = APIRouter(prefix="/admin/portal", tags=["admin-portal"])
portal_router.include_router(users.router)
portal_router.include_router(chat_insights.router)
portal_router.include_router(ops.router)
portal_router.include_router(address_quality.router)
portal_router.include_router(analytics.router)
portal_router.include_router(feedback.router)


@portal_router.get("", response_model=None)
def dashboard(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect

    since = window_start(7)
    user_turns = ChatLog.role == "user"

    chat_totals = db.execute(
        select(
            func.count(),
            func.count(func.distinct(ChatLog.session_id)),
            func.avg(ChatLog.latency_ms),
        ).where(user_turns, ChatLog.created_at >= since)
    ).one()
    messages, sessions, avg_latency = chat_totals

    failed_jobs = int(
        db.execute(select(func.count()).select_from(Job).where(Job.status == "failed")).scalar()
        or 0
    )
    stuck_outbox = int(
        db.execute(
            select(func.count())
            .select_from(Outbox)
            .where(Outbox.state.in_(("pending", "failed")))
        ).scalar()
        or 0
    )
    failed_outbox = int(
        db.execute(
            select(func.count()).select_from(Outbox).where(Outbox.state == "failed")
        ).scalar()
        or 0
    )
    total_users = int(db.execute(select(func.count()).select_from(User)).scalar() or 0)

    return render(
        request,
        "portal_dashboard.html",
        "dashboard",
        {
            "cards": queue_cards(db),
            "messages": int(messages or 0),
            "sessions": int(sessions or 0),
            "avg_latency": round(avg_latency) if avg_latency is not None else None,
            "failed_jobs": failed_jobs,
            "stuck_outbox": stuck_outbox,
            "failed_outbox": failed_outbox,
            "total_users": total_users,
        },
    )


@portal_router.get("/moderation", response_model=None)
def moderation_hub(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    return render(request, "portal_moderation.html", "moderation", {"cards": queue_cards(db)})


@portal_router.get("/audit", response_model=None)
def audit_log(
    request: Request, page: int = 1, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    enabled = audit_enabled(db)
    rows: list[AdminAuditLog] = []
    if enabled:
        page = max(1, page)
        rows = list(
            db.execute(
                select(AdminAuditLog)
                .order_by(desc(AdminAuditLog.created_at))
                .offset((page - 1) * 100)
                .limit(100)
            )
            .scalars()
            .all()
        )
    return render(
        request,
        "portal_audit.html",
        "audit",
        {
            "enabled": enabled,
            "rows": rows,
            "page": page,
            "table_name": audit_models.AUDIT_TABLE_NAME,
        },
    )
