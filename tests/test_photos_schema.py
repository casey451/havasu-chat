"""Phase 2B.1 — ``photos`` table + ORM wiring."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as SqlSession

from app.db.database import SessionLocal, engine
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Photo, User


def _now() -> datetime:
    return datetime.now(UTC)


def test_photos_table_exists_after_migration() -> None:
    insp = inspect(engine)
    assert insp.has_table("photos")
    cols = {c["name"]: c for c in insp.get_columns("photos")}
    for name in (
        "id",
        "entity_id",
        "uploaded_by_user_id",
        "mime_type",
        "storage_key",
        "status",
        "is_hero",
        "display_order",
        "created_at",
        "updated_at",
    ):
        assert name in cols


@pytest.mark.parametrize(
    ("col", "expect_nullable"),
    [
        ("cdn_url", True),
        ("thumbnail_url", True),
        ("image_hash", True),
        ("mime_type", False),
        ("storage_key", False),
    ],
)
def test_photos_column_nullability(col: str, expect_nullable: bool) -> None:
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("photos")}
    assert cols[col]["nullable"] is expect_nullable


def test_photos_status_check_constraint() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    eid = ""
    uemail = ""
    with SessionLocal() as db:
        e, u = _entity_and_user(db, suf)
        eid, uemail = e.id, u.email
        db.add(
            Photo(
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key="x",
                status="bogus",
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    with SessionLocal() as db:
        db.query(Photo).filter(Photo.entity_id == eid).delete()
        u2 = db.query(User).filter(User.email == uemail).first()
        if u2:
            db.delete(u2)
        e2 = db.get(Entity, eid)
        if e2:
            db.delete(e2)
        db.commit()


def test_photos_mime_type_check_constraint() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    eid = ""
    uemail = ""
    with SessionLocal() as db:
        e, u = _entity_and_user(db, suf)
        eid, uemail = e.id, u.email
        db.add(
            Photo(
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/gif",
                storage_key="x",
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    with SessionLocal() as db:
        db.query(Photo).filter(Photo.entity_id == eid).delete()
        u2 = db.query(User).filter(User.email == uemail).first()
        if u2:
            db.delete(u2)
        e2 = db.get(Entity, eid)
        if e2:
            db.delete(e2)
        db.commit()


def _entity_and_user(db: SqlSession, suf: str) -> tuple[Entity, User]:
    e = Entity(
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=f"photo-ent-{suf}",
        name=f"PhotoEnt {suf}",
        source="test-photos",
    )
    db.add(e)
    u = User(
        email=f"u-{suf}@example.com",
        display_name="U",
    )
    db.add(u)
    db.commit()
    db.refresh(e)
    db.refresh(u)
    return e, u


def test_photos_fk_entity_cascade_delete() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        e, u = _entity_and_user(db, suf)
        pid = uuid.uuid4().hex
        db.add(
            Photo(
                id=pid,
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key="k/",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        assert db.get(Photo, pid) is not None
        db.delete(e)
        db.commit()
        db.expire_all()
        assert db.get(Photo, pid) is None
    engine.dispose()


def test_photos_fk_user_cascade_delete() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        e, u = _entity_and_user(db, suf)
        pid = uuid.uuid4().hex
        db.add(
            Photo(
                id=pid,
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key="k/",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        db.delete(u)
        db.commit()
        db.expire_all()
        assert db.get(Photo, pid) is None
        db.delete(e)
        db.commit()
    engine.dispose()


def test_photos_indexes_exist() -> None:
    insp = inspect(engine)
    ix = {i["name"] for i in insp.get_indexes("photos")}
    for name in (
        "ix_photos_entity_id",
        "ix_photos_uploaded_by_user_id",
        "ix_photos_status",
        "ix_photos_image_hash",
        "ix_photos_entity_hash_status",
    ):
        assert name in ix


def test_entity_photos_relationship_filters_live_only() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        e, u = _entity_and_user(db, suf)
        db.add(
            Photo(
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key="a/",
                status="live",
                display_order=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Photo(
                entity_id=e.id,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key="b/",
                status="uploading",
                display_order=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        ent = db.query(Entity).filter_by(id=e.id).first()
        assert ent is not None
        rel = [p.status for p in ent.photos]
        assert rel == ["live"]
        db.query(Photo).filter(Photo.entity_id == e.id).delete()
        db.delete(u)
        db.delete(e)
        db.commit()
