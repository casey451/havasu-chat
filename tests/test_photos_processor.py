"""Phase 2B.1 — Pillow pipeline stages + orchestrator."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

import pytest
from PIL import Image

from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Photo, User
from app.photos import processor as proc


def _rgb_jpeg(w: int = 256, h: int = 256, color: tuple[int, int, int] = (90, 120, 33)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_decode_accepts_valid_jpeg() -> None:
    raw = _rgb_jpeg()
    r = proc.decode_and_validate(raw, declared_mime="image/jpeg")
    assert not isinstance(r, proc.ProcessingError)
    assert r.size[0] >= 128


def test_decode_rejects_all_black() -> None:
    raw = _rgb_jpeg(200, 200, color=(0, 0, 0))
    r = proc.decode_and_validate(raw, declared_mime="image/jpeg")
    assert isinstance(r, proc.ProcessingError)
    assert r.code == "decode_failed"


def test_decode_rejects_too_small() -> None:
    raw = _rgb_jpeg(64, 64)
    r = proc.decode_and_validate(raw, declared_mime="image/jpeg")
    assert isinstance(r, proc.ProcessingError)
    assert r.code == "too_small"


def test_decode_rejects_non_image() -> None:
    r = proc.decode_and_validate(b"not an image", declared_mime="image/jpeg")
    assert isinstance(r, proc.ProcessingError)
    assert r.code == "decode_failed"


def test_strip_exif_removes_exif_segment() -> None:
    raw = _rgb_jpeg()
    img = Image.open(io.BytesIO(raw))
    stripped = proc.strip_exif(img)
    assert not isinstance(stripped, proc.ProcessingError)
    ex = stripped.getexif()
    assert ex is None or len(ex) == 0


def test_compute_hash_deterministic() -> None:
    raw = _rgb_jpeg()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    a = proc.compute_hash(img)
    b = proc.compute_hash(img)
    assert a == b
    assert len(a) == 64


def test_generate_variants_sizes_and_formats() -> None:
    raw = _rgb_jpeg(400, 400)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    v = proc.generate_variants(img)
    assert not isinstance(v, proc.ProcessingError)
    assert set(v.keys()) == {"thumbnail", "medium", "hero"}
    for name, sizes in (
        ("thumbnail", (256, 256)),
        ("medium", (512, 512)),
        ("hero", (1280, 720)),
    ):
        w = Image.open(io.BytesIO(v[name]["webp"]))
        assert w.size == sizes
    assert len(v["thumbnail"]["webp"]) > 0
    assert len(v["thumbnail"]["jpeg"]) > 0


def test_process_uploaded_photo_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime.now(UTC).replace(tzinfo=None)

    def fake_upload(key: str, content: bytes, content_type: str) -> str:
        return f"https://pub-test.r2.dev/{key}"

    monkeypatch.setattr(proc, "upload_bytes", fake_upload)

    e_id = u_id = ""
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"pip-{suf}",
            name="P",
            source="t",
            created_at=now,
            updated_at=now,
        )
        u = User(email=f"p-{suf}@example.com")
        db.add(e)
        db.add(u)
        db.commit()
        db.refresh(e)
        db.refresh(u)
        e_id, u_id = e.id, u.id
        pid = str(uuid.uuid4())
        db.add(
            Photo(
                id=pid,
                entity_id=e_id,
                uploaded_by_user_id=u_id,
                mime_type="image/jpeg",
                storage_key="",
                status="uploading",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    proc.process_uploaded_photo(pid, _rgb_jpeg(), "image/jpeg")

    with SessionLocal() as db:
        row = db.get(Photo, pid)
        assert row is not None
        assert row.status == "live"
        assert row.hero_url and "hero.webp" in row.hero_url
        assert row.image_hash
        db.delete(row)
        db.delete(db.get(User, u_id))
        db.delete(db.get(Entity, e_id))
        db.commit()


def test_process_uploaded_photo_duplicate_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime.now(UTC).replace(tzinfo=None)

    def fake_upload(key: str, content: bytes, content_type: str) -> str:
        return f"https://pub-test.r2.dev/{key}"

    monkeypatch.setattr(proc, "upload_bytes", fake_upload)
    jpeg = _rgb_jpeg(color=(11, 22, 33))

    e_id = u_id = ""
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"dup-{suf}",
            name="D",
            source="t",
            created_at=now,
            updated_at=now,
        )
        u = User(email=f"d-{suf}@example.com")
        db.add(e)
        db.add(u)
        db.commit()
        db.refresh(e)
        db.refresh(u)
        e_id, u_id = e.id, u.id
        stripped = proc.strip_exif(Image.open(io.BytesIO(jpeg)))
        assert not isinstance(stripped, proc.ProcessingError)
        h = proc.compute_hash(stripped)
        p1 = str(uuid.uuid4())
        p2 = str(uuid.uuid4())
        db.add(
            Photo(
                id=p1,
                entity_id=e_id,
                uploaded_by_user_id=u_id,
                mime_type="image/jpeg",
                storage_key="p/",
                status="live",
                image_hash=h,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Photo(
                id=p2,
                entity_id=e_id,
                uploaded_by_user_id=u_id,
                mime_type="image/jpeg",
                storage_key="",
                status="uploading",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    proc.process_uploaded_photo(p2, jpeg, "image/jpeg")
    with SessionLocal() as db:
        r2 = db.get(Photo, p2)
        assert r2 is not None
        assert r2.status == "flagged"
        assert r2.processing_error == "duplicate"
        db.delete(db.get(Photo, p1))
        db.delete(r2)
        db.delete(db.get(User, u_id))
        db.delete(db.get(Entity, e_id))
        db.commit()


def test_process_uploaded_photo_r2_failure_leaves_uploading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime.now(UTC).replace(tzinfo=None)

    def boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(proc, "upload_bytes", boom)

    e_id = u_id = ""
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"r2f-{suf}",
            name="R",
            source="t",
            created_at=now,
            updated_at=now,
        )
        u = User(email=f"r-{suf}@example.com")
        db.add(e)
        db.add(u)
        db.commit()
        db.refresh(e)
        db.refresh(u)
        e_id, u_id = e.id, u.id
        pid = str(uuid.uuid4())
        db.add(
            Photo(
                id=pid,
                entity_id=e_id,
                uploaded_by_user_id=u_id,
                mime_type="image/jpeg",
                storage_key="",
                status="uploading",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    proc.process_uploaded_photo(pid, _rgb_jpeg(), "image/jpeg")
    with SessionLocal() as db:
        row = db.get(Photo, pid)
        assert row is not None
        assert row.status == "uploading"
        db.delete(row)
        db.delete(db.get(User, u_id))
        db.delete(db.get(Entity, e_id))
        db.commit()
