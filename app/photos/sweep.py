"""Stuck-upload sweep for Photo rows left in ``uploading`` after R2 failures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as SqlSession

from app.db.database import SessionLocal
from app.db.models import Photo


def run_stuck_photo_sweep() -> int:
    """Flip ``uploading`` rows older than 24h to ``flagged`` + ``decode_failed``.

    Returns the number of rows updated (logging / tests).
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
    with SessionLocal() as db:
        return _run_stuck_photo_sweep_session(db, cutoff=cutoff)


def _run_stuck_photo_sweep_session(db: SqlSession, *, cutoff: datetime) -> int:
    stuck = db.query(Photo).filter(Photo.status == "uploading", Photo.created_at < cutoff).all()
    for p in stuck:
        p.status = "flagged"
        p.processing_error = "decode_failed"
    db.commit()
    return len(stuck)
