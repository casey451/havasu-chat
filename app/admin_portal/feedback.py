"""Feedback queue — the admin-visible side of the DB-backed feedback channel.

Lists submissions from the ``feedback`` table (P5, §2.4) with a status filter
and a one-click triage action (mark reviewed / resolved / spam). Every status
change records an audit row when the audit table exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin_portal.audit_models import record_audit
from app.admin_portal.guard import guard
from app.admin_portal.shared import render
from app.db.database import get_db
from app.feedback.store import (
    VALID_STATUSES,
    count_feedback,
    list_feedback,
    status_counts,
    update_feedback_status,
)

router = APIRouter()

PAGE_SIZE = 100


@router.get("/feedback", response_model=None)
def feedback_list(
    request: Request,
    status: str = "new",
    page: int = 1,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    status_filter = status if status in VALID_STATUSES else None
    page = max(1, page)
    rows = list_feedback(
        db, status=status_filter, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )
    total = count_feedback(db, status=status_filter)
    return render(
        request,
        "portal_feedback.html",
        "feedback",
        {
            "rows": rows,
            "status": status,
            "statuses": sorted(VALID_STATUSES),
            "counts": status_counts(db),
            "total": total,
            "page": page,
            "pages": max(1, -(-total // PAGE_SIZE)),
        },
    )


@router.post("/feedback/{feedback_id}/status", response_model=None)
def feedback_set_status(
    request: Request,
    feedback_id: int,
    new_status: str = Form(...),
    note: str = Form(""),
    return_status: str = Form("new"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    row = update_feedback_status(
        db, feedback_id, status=new_status, admin_note=note or None
    )
    if row is not None:
        record_audit(
            db,
            action="feedback.status",
            target_type="feedback",
            target_id=str(feedback_id),
            detail=f"-> {new_status}",
        )
        db.commit()
    return RedirectResponse(
        url=f"/admin/portal/feedback?status={return_status}", status_code=303
    )
