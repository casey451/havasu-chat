"""P5 — 12-month query_log retention truncation (plan §2.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import QueryLog
from app.v1.query_log import purge_old_query_logs


def _row(db, *, intent, age_days):
    r = QueryLog(
        normalized_intent=intent,
        result_count=1,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=age_days),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_purge_dry_run_counts_but_keeps_rows() -> None:
    tag = f"ret-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        old = _row(db, intent=f"{tag}-old", age_days=400)
        fresh = _row(db, intent=f"{tag}-fresh", age_days=5)
        try:
            would = purge_old_query_logs(db, older_than_days=365, dry_run=True)
            assert would >= 1
            # Dry run deletes nothing.
            assert db.get(QueryLog, old.id) is not None
            assert db.get(QueryLog, fresh.id) is not None
        finally:
            db.execute(
                delete(QueryLog).where(QueryLog.normalized_intent.like(f"{tag}-%"))
            )
            db.commit()


def test_purge_apply_deletes_only_old_rows() -> None:
    tag = f"ret-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        old = _row(db, intent=f"{tag}-old", age_days=400)
        fresh = _row(db, intent=f"{tag}-fresh", age_days=5)
        old_id, fresh_id = old.id, fresh.id
        try:
            deleted = purge_old_query_logs(db, older_than_days=365, dry_run=False)
            assert deleted >= 1
            assert db.get(QueryLog, old_id) is None
            assert db.get(QueryLog, fresh_id) is not None
            # Only our old row should be gone among this tag's rows.
            remaining = db.scalars(
                select(QueryLog.normalized_intent).where(
                    QueryLog.normalized_intent.like(f"{tag}-%")
                )
            ).all()
            assert f"{tag}-fresh" in remaining
            assert f"{tag}-old" not in remaining
        finally:
            db.execute(
                delete(QueryLog).where(QueryLog.normalized_intent.like(f"{tag}-%"))
            )
            db.commit()
