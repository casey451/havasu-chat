"""Admin JSON API for the Jobs portal (session-cookie auth).

People use the cookie, machines use the bearer token — so the *create* and
*history* endpoints here share the same admin session cookie as
``admin_contributions``; the worker-facing claim/patch endpoints live in
``app.api.routes.ingest_jobs`` behind the ingest token. See ADMIN_JOBS_SPEC.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.db.database import get_db
from app.db.jobs_store import VALID_JOB_TYPES, create_job, list_jobs
from app.db.models import Job

router = APIRouter(prefix="/api/admin", tags=["admin-jobs"])


def require_admin(request: Request) -> None:
    """Same session cookie as the HTML admin (``POST /admin/login``)."""
    if not verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )


AdminAuth = Annotated[None, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_db)]


class JobCreate(BaseModel):
    job_type: str
    params: dict | None = None


class JobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    requested_by: str | None
    claimed_by: str | None
    params: dict | None
    result_summary: str | None
    created_at: datetime | None
    claimed_at: datetime | None
    finished_at: datetime | None


def _serialize(row: Job) -> JobResponse:
    return JobResponse(
        id=row.id,
        job_type=row.job_type,
        status=row.status,
        requested_by=row.requested_by,
        claimed_by=row.claimed_by,
        params=row.params,
        result_summary=row.result_summary,
        created_at=row.created_at,
        claimed_at=row.claimed_at,
        finished_at=row.finished_at,
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def post_job(_: AdminAuth, db: DbSession, body: JobCreate) -> JobResponse:
    """Queue a job. 422 on an unknown ``job_type`` (CHECK constraint also guards it)."""
    if body.job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown job_type: {body.job_type}",
        )
    row = create_job(db, body.job_type, params=body.params, requested_by="admin")
    return _serialize(row)


@router.get("/jobs", response_model=list[JobResponse])
def get_jobs(
    _: AdminAuth,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JobResponse]:
    """Job history for the UI, newest first."""
    return [_serialize(r) for r in list_jobs(db, limit=limit)]
