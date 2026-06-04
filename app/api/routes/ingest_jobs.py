"""Worker-facing Jobs API — claim + report (machine-ingest bearer token).

OpenClaw / Cowork crons poll ``GET /api/ingest/jobs/pending?worker=...`` with the
``INGEST_API_TOKEN`` bearer (the same door as ``ingest`` / ``captures``). The poll
is deliberately dumb: a 204 means "nothing for you, go back to sleep"; a 200 with a
job body means "wake the model and do this." When a job is returned it has already
been atomically marked ``claimed``. Workers then PATCH ``/api/ingest/jobs/{id}`` to
report ``running`` / ``done`` / ``failed``. See ADMIN_JOBS_SPEC.md.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.ingest import require_ingest_token
from app.db.database import get_db
from app.db.jobs_store import (
    PATCHABLE_STATUSES,
    WORKER_TYPE_MAP,
    claim_next_job,
    finish_job,
)
from app.db.models import Job

router = APIRouter(prefix="/api/ingest", tags=["ingest-jobs"])

IngestAuth = Annotated[None, Depends(require_ingest_token)]
DbSession = Annotated[Session, Depends(get_db)]


class JobPatch(BaseModel):
    status: str
    result_summary: str | None = None


def _serialize(row: Job) -> dict:
    return {
        "id": row.id,
        "job_type": row.job_type,
        "status": row.status,
        "requested_by": row.requested_by,
        "claimed_by": row.claimed_by,
        "params": row.params,
        "result_summary": row.result_summary,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


@router.get("/jobs/pending", response_model=None)
def get_pending_job(
    _: IngestAuth,
    db: DbSession,
    response: Response,
    worker: Annotated[str, Query()],
) -> dict | Response:
    """Atomically claim + return the oldest queued job for ``worker``.

    200 + job JSON when one was claimed; 204 (empty) when the queue is empty for
    this worker — so a plain ``curl`` can branch on the status code with no AI.
    422 on an unknown worker name.
    """
    if worker not in WORKER_TYPE_MAP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown worker: {worker}. Expected one of {sorted(WORKER_TYPE_MAP)}.",
        )
    row = claim_next_job(db, worker)
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return _serialize(row)


@router.patch("/jobs/{job_id}")
def patch_job(
    _: IngestAuth,
    job_id: str,
    payload: JobPatch,
    db: DbSession,
) -> dict:
    """Report job progress. Accepts ``running`` / ``done`` / ``failed`` only; 404 if missing."""
    if payload.status not in PATCHABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {sorted(PATCHABLE_STATUSES)}.",
        )
    row = finish_job(db, job_id, payload.status, result_summary=payload.result_summary)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    return _serialize(row)
