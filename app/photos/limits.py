"""Upload caps: per-uploader daily count + per-entity live/uploading count."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session as SqlSession

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE
from app.db.models import Photo


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def check_uploader_daily_cap(db: SqlSession, user_id: str, *, limit: int = 20) -> bool:
    """Return True when uploader has reached ``limit`` rows in the rolling 24h window."""
    cutoff = _naive_utc_now() - timedelta(hours=24)
    cnt = (
        db.query(func.count(Photo.id))
        .filter(Photo.uploaded_by_user_id == user_id, Photo.created_at >= cutoff)
        .scalar()
    )
    return int(cnt or 0) >= limit


def check_entity_photo_cap(
    db: SqlSession, entity_id: str, entity_type: str, *, limit: int | None = None
) -> bool:
    """Return True when entity is at or over its photo cap (live + uploading)."""
    if limit is None:
        if entity_type == ENTITY_TYPE_COMMERCIAL:
            limit = 100
        elif entity_type == ENTITY_TYPE_PLACE:
            limit = 50
        else:
            limit = 0
    cnt = (
        db.query(func.count(Photo.id))
        .filter(
            Photo.entity_id == entity_id,
            Photo.status.in_(("live", "uploading")),
        )
        .scalar()
    )
    return int(cnt or 0) >= limit
