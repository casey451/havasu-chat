"""Ops — monitor the jobs queue and the must-not-lose outbox.

Failed outbox rows are dropped magic links / notifications; this page
makes them visible and retryable. Failed jobs get a one-click requeue.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin_portal.audit_models import record_audit
from app.admin_portal.guard import guard
from app.admin_portal.shared import render
from app.db.database import get_db
from app.db.models import Job, Outbox

router = APIRouter()

JOB_STATUSES = ("queued", "claimed", "running", "done", "failed")
OUTBOX_STATES = ("pending", "in_flight", "delivered", "failed")


def _status_counts(db: Session, column, keys: tuple[str, ...]) -> dict[str, int]:
    rows = dict(db.execute(select(column, func.count()).group_by(column)).all())
    return {k: int(rows.get(k, 0)) for k in keys}


@router.get("/ops", response_model=None)
def ops_home(
    request: Request,
    job_status: str = "",
    outbox_state: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect

    jobs_stmt = select(Job).order_by(desc(Job.created_at)).limit(50)
    if job_status in JOB_STATUSES:
        jobs_stmt = (
            select(Job).where(Job.status == job_status).order_by(desc(Job.created_at)).limit(50)
        )

    outbox_stmt = select(Outbox).order_by(desc(Outbox.created_at)).limit(50)
    if outbox_state in OUTBOX_STATES:
        outbox_stmt = (
            select(Outbox)
            .where(Outbox.state == outbox_state)
            .order_by(desc(Outbox.created_at))
            .limit(50)
        )

    return render(
        request,
        "portal_ops.html",
        "ops",
        {
            "job_counts": _status_counts(db, Job.status, JOB_STATUSES),
            "outbox_counts": _status_counts(db, Outbox.state, OUTBOX_STATES),
            "jobs": db.execute(jobs_stmt).scalars().all(),
            "outbox_rows": db.execute(outbox_stmt).scalars().all(),
            "job_status": job_status,
            "outbox_state": outbox_state,
            "job_statuses": JOB_STATUSES,
            "outbox_states": OUTBOX_STATES,
        },
    )


@router.post("/ops/jobs/{job_id}/requeue", response_model=None)
def requeue_job(
    request: Request, job_id: str, db: Session = Depends(get_db)
) -> RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "failed":
        raise HTTPException(status_code=400, detail="only failed jobs can be requeued")
    job.status = "queued"
    job.claimed_by = None
    job.claimed_at = None
    job.finished_at = None
    record_audit(
        db, action="job.requeue", target_type="job", target_id=job_id, detail=job.job_type
    )
    db.commit()
    return RedirectResponse(url="/admin/portal/ops", status_code=303)


@router.post("/ops/outbox/{row_id}/retry", response_model=None)
def retry_outbox(
    request: Request, row_id: str, db: Session = Depends(get_db)
) -> RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    row = db.get(Outbox, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="outbox row not found")
    if row.state != "failed":
        raise HTTPException(status_code=400, detail="only failed rows can be retried")
    row.state = "pending"
    row.last_error = None
    record_audit(
        db, action="outbox.retry", target_type="outbox", target_id=row_id, detail=row.kind
    )
    db.commit()
    return RedirectResponse(url="/admin/portal/ops", status_code=303)
