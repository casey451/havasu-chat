"""CRUD + atomic-claim helpers for the admin Jobs portal (``jobs`` table).

The Jobs page queues work; worker agents poll and claim it. The only subtle
piece is :func:`claim_next_job`, which must be safe under concurrent polling:
two workers (or two polls of the same worker) must never claim the same job.
We use a guarded ``UPDATE ... WHERE id = :id AND status = 'queued'`` and trust
the row count — the loser of a race updates zero rows and simply looks again.
This is the portable "or equivalent" of ``UPDATE ... RETURNING`` and works the
same on SQLite (tests) and Postgres (prod).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.db.models import Job

# Job types each worker is allowed to claim (ADMIN_JOBS_SPEC.md + kickoff addition
# 1a: ``discovery_audit`` joins the Cowork set). OpenClaw = hands (FB capture only);
# Cowork = brain (everything else).
WORKER_TYPE_MAP: dict[str, tuple[str, ...]] = {
    "openclaw": ("fb_capture_sweep",),
    "cowork": (
        "schedule_hunt",
        "capture_review",
        "publish_approved",
        "discovery_audit",
    ),
}

VALID_JOB_TYPES: frozenset[str] = frozenset(
    t for types in WORKER_TYPE_MAP.values() for t in types
)
VALID_STATUSES: frozenset[str] = frozenset(
    {"queued", "claimed", "running", "done", "failed"}
)
# Statuses a worker may PATCH a job into (forward progress only — never back to
# ``queued``, and ``claimed`` is owned by the claim endpoint).
PATCHABLE_STATUSES: frozenset[str] = frozenset({"running", "done", "failed"})
# Job types still "occupying" a slot, used by the UI to disable a button while
# the same type is already in flight.
ACTIVE_STATUSES: frozenset[str] = frozenset({"queued", "claimed", "running"})


def create_job(
    db: Session,
    job_type: str,
    *,
    params: dict | None = None,
    requested_by: str | None = None,
) -> Job:
    """Insert one ``queued`` job. Caller is responsible for validating ``job_type``."""
    row = Job(
        job_type=job_type,
        status="queued",
        params=params,
        requested_by=requested_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_jobs(db: Session, *, limit: int = 50) -> list[Job]:
    """Job history, newest first (for the admin UI / history endpoint)."""
    stmt = select(Job).order_by(Job.created_at.desc(), Job.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def active_job_types(db: Session) -> set[str]:
    """The set of job types with a queued/claimed/running row (UI button-disable)."""
    stmt = select(Job.job_type).where(Job.status.in_(tuple(ACTIVE_STATUSES))).distinct()
    return {str(t) for t in db.execute(stmt).scalars().all()}


def claim_next_job(db: Session, worker: str) -> Job | None:
    """Atomically claim the oldest queued job matching ``worker``'s type map.

    Returns the now-``claimed`` job, or ``None`` if the queue holds nothing for
    this worker. Safe under concurrent polling: the guarded UPDATE means at most
    one caller wins each row; a loser retries against the next candidate.
    """
    allowed = WORKER_TYPE_MAP.get(worker)
    if not allowed:
        return None

    while True:
        candidate_id = db.execute(
            select(Job.id)
            .where(Job.status == "queued", Job.job_type.in_(allowed))
            .order_by(Job.created_at.asc(), Job.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        if candidate_id is None:
            return None

        now = datetime.now(UTC)
        result = db.execute(
            update(Job)
            .where(Job.id == candidate_id, Job.status == "queued")
            .values(status="claimed", claimed_by=worker, claimed_at=now)
        )
        db.commit()
        # Session.execute(update(...)) returns a CursorResult at runtime, but is
        # typed as the base Result (no rowcount). Cast to read the DML row count.
        if cast("CursorResult[Any]", result).rowcount == 1:
            return db.get(Job, candidate_id)
        # Lost the race for this row — another worker claimed it first. Look again.


def finish_job(
    db: Session,
    job_id: str,
    status: str,
    *,
    result_summary: str | None = None,
) -> Job | None:
    """Update a job's status (and optional summary). Returns ``None`` if missing.

    Stamps ``finished_at`` on terminal states (``done`` / ``failed``). Raises
    ``ValueError`` on an out-of-vocabulary status so the route can 422.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    row = db.get(Job, job_id)
    if row is None:
        return None
    row.status = status
    if result_summary is not None:
        row.result_summary = result_summary
    if status in ("done", "failed"):
        row.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row
