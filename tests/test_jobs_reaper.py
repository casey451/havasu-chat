"""OPS-4: stale-claim reaper (jobs janitor) — store helpers + main.py wrapper.

Audit: docs/AUDIT_SECURITY_PERF_OPS_2026-06-10.md:189-193.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.admin_portal.audit_models import AdminAuditLog
from app.db.database import SessionLocal
from app.db.jobs_store import (
    claim_next_job,
    count_stale_running,
    create_job,
    requeue_stale_claims,
)
from app.db.models import Job
from app.main import run_stale_job_requeue


@pytest.fixture(autouse=True)
def _clean_tables():
    with SessionLocal() as db:
        db.execute(delete(Job))
        db.execute(delete(AdminAuditLog))
        db.commit()
    yield


def _mk(db: Session, status: str, *, age_minutes: int = 0, job_type: str = "schedule_hunt") -> Job:
    row = create_job(db, job_type)
    row.status = status
    if status in ("claimed", "running"):
        row.claimed_by = "cowork"
        row.claimed_at = datetime.now(UTC) - timedelta(minutes=age_minutes)
    db.commit()
    db.refresh(row)
    return row


def test_stale_claimed_requeued_and_claim_fields_cleared():
    with SessionLocal() as db:
        stale = _mk(db, "claimed", age_minutes=120)
        requeued = requeue_stale_claims(db, older_than_minutes=60)
        assert [j.id for j in requeued] == [stale.id]
        db.refresh(stale)
        assert stale.status == "queued"
        assert stale.claimed_by is None
        assert stale.claimed_at is None
        assert stale.finished_at is None


def test_fresh_claimed_untouched():
    with SessionLocal() as db:
        fresh = _mk(db, "claimed", age_minutes=5)
        assert requeue_stale_claims(db, older_than_minutes=60) == []
        db.refresh(fresh)
        assert fresh.status == "claimed"
        assert fresh.claimed_by == "cowork"


def test_running_and_terminal_states_never_requeued():
    with SessionLocal() as db:
        running = _mk(db, "running", age_minutes=600)
        done = _mk(db, "done")
        failed = _mk(db, "failed")
        assert requeue_stale_claims(db, older_than_minutes=60) == []
        for row in (running, done, failed):
            db.refresh(row)
        assert running.status == "running"
        assert done.status == "done"
        assert failed.status == "failed"


def test_stale_requeue_writes_audit_row():
    with SessionLocal() as db:
        stale = _mk(db, "claimed", age_minutes=120, job_type="capture_review")
        requeue_stale_claims(db, older_than_minutes=60)
        rows = (
            db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "job.requeue_stale"))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].target_type == "job"
        assert rows[0].target_id == str(stale.id)
        assert rows[0].detail == "capture_review"


def test_count_stale_running_thresholds():
    with SessionLocal() as db:
        _mk(db, "running", age_minutes=600)  # 10h — stale
        _mk(db, "running", age_minutes=30)  # fresh
        assert count_stale_running(db, older_than_hours=6) == 1


def test_requeued_job_is_claimable_again():
    with SessionLocal() as db:
        _mk(db, "claimed", age_minutes=120)
        requeue_stale_claims(db, older_than_minutes=60)
        again = claim_next_job(db, "cowork")
        assert again is not None
        assert again.status == "claimed"


def test_main_wrapper_requeues_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("JOBS_STALE_CLAIM_MINUTES", "60")
    with SessionLocal() as db:
        _mk(db, "claimed", age_minutes=120)
    assert run_stale_job_requeue() == 1
    assert run_stale_job_requeue() == 0


def test_main_wrapper_garbage_env_falls_back(monkeypatch):
    monkeypatch.setenv("JOBS_STALE_CLAIM_MINUTES", "banana")
    with SessionLocal() as db:
        _mk(db, "claimed", age_minutes=120)  # stale vs the 60-min default
    assert run_stale_job_requeue() == 1
