"""Phase 2B.1 — stuck-upload sweep."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Photo, User
from app.photos.sweep import _run_stuck_photo_sweep_session


def test_sweep_flags_uploading_older_than_24h() -> None:
    suf = uuid.uuid4().hex[:8]
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=25)
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(hours=24)
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"sw-{suf}",
            name="S",
            source="t",
            created_at=now,
            updated_at=now,
        )
        u = User(email=f"s-{suf}@example.com")
        db.add(e)
        db.add(u)
        db.commit()
        db.refresh(e)
        db.refresh(u)
        pid = str(uuid.uuid4())
        db.add(
            Photo(
                id=pid,
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key="",
                status="uploading",
                created_at=old,
                updated_at=old,
            )
        )
        db.commit()
        n = _run_stuck_photo_sweep_session(db, cutoff=cutoff)
        assert n == 1
        row = db.get(Photo, pid)
        assert row is not None
        assert row.status == "flagged"
        assert row.processing_error == "decode_failed"
        db.delete(row)
        db.delete(db.get(User, u.id))
        db.delete(db.get(Entity, e.id))
        db.commit()


def test_sweep_leaves_recent_uploading() -> None:
    suf = uuid.uuid4().hex[:8]
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(hours=24)
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"sw2-{suf}",
            name="S2",
            source="t",
            created_at=now,
            updated_at=now,
        )
        u = User(email=f"s2-{suf}@example.com")
        db.add(e)
        db.add(u)
        db.commit()
        db.refresh(e)
        db.refresh(u)
        pid = str(uuid.uuid4())
        db.add(
            Photo(
                id=pid,
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key="",
                status="uploading",
                created_at=recent,
                updated_at=recent,
            )
        )
        db.commit()
        n = _run_stuck_photo_sweep_session(db, cutoff=cutoff)
        assert n == 0
        row = db.get(Photo, pid)
        assert row is not None
        assert row.status == "uploading"
        db.delete(row)
        db.delete(db.get(User, u.id))
        db.delete(db.get(Entity, e.id))
        db.commit()
