"""Authenticated photo upload + lifecycle API (Phase 2B.1)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as SqlSession

from app.auth.claims import find_existing_claim
from app.auth.dependencies import require_user
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE
from app.db.models import Entity, Photo, User
from app.photos.limits import check_entity_photo_cap, check_uploader_daily_cap
from app.photos.processor import process_uploaded_photo

router = APIRouter(tags=["photos"])

ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _user_can_manage_photo(db: SqlSession, user: User, photo: Photo) -> bool:
    if user.role == "admin":
        return True
    if photo.uploaded_by_user_id == user.id:
        return True
    claim = find_existing_claim(db, user.id, photo.entity_id)
    return claim is not None and claim.status == "verified"


def _require_verified_claim_or_admin(db: SqlSession, user: User, entity_id: str) -> None:
    if user.role == "admin":
        return
    claim = find_existing_claim(db, user.id, entity_id)
    if claim is None or claim.status != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="claim_not_verified",
        )


@router.post("/api/entities/{entity_id}/photos", status_code=201)
@limiter.limit("50/day")
async def upload_photo(
    request: Request,
    entity_id: str,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(require_user)],
    db: Annotated[SqlSession, Depends(get_db)],
    caption: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    if entity.entity_type not in (ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE):
        raise HTTPException(
            status_code=400,
            detail="entity_not_photo_uploadable",
        )

    _require_verified_claim_or_admin(db, current_user, entity_id)

    if (file.content_type or "") not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="unsupported_mime_type")

    content = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="file_too_large")

    if check_entity_photo_cap(db, entity_id, entity.entity_type):
        raise HTTPException(status_code=429, detail="entity_photo_cap_exceeded")
    if check_uploader_daily_cap(db, current_user.id):
        raise HTTPException(status_code=429, detail="uploader_daily_cap_exceeded")

    photo = Photo(
        entity_id=entity_id,
        uploaded_by_user_id=current_user.id,
        original_filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        storage_key="",
        caption=caption,
        status="uploading",
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    background_tasks.add_task(
        process_uploaded_photo,
        photo_id=photo.id,
        content=content,
        declared_mime=file.content_type or "",
    )

    return {"photo_id": photo.id, "status": "uploading"}


@router.delete("/api/photos/{photo_id}", status_code=200)
def delete_photo(
    photo_id: str,
    current_user: Annotated[User, Depends(require_user)],
    db: Annotated[SqlSession, Depends(get_db)],
) -> dict[str, str]:
    row = db.get(Photo, photo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="photo_not_found")
    if not _user_can_manage_photo(db, current_user, row):
        raise HTTPException(status_code=403, detail="forbidden")
    if row.status == "deleted":
        return {"photo_id": row.id, "status": "deleted"}
    row.status = "deleted"
    row.processing_error = "user_deleted"
    db.add(row)
    db.commit()
    return {"photo_id": row.id, "status": "deleted"}


@router.post("/api/photos/{photo_id}/set-hero", status_code=200)
def set_hero_photo(
    photo_id: str,
    current_user: Annotated[User, Depends(require_user)],
    db: Annotated[SqlSession, Depends(get_db)],
) -> dict[str, Any]:
    row = db.get(Photo, photo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="photo_not_found")
    if row.status != "live":
        raise HTTPException(status_code=400, detail="photo_not_live")
    if not _user_can_manage_photo(db, current_user, row):
        raise HTTPException(status_code=403, detail="forbidden")

    siblings = (
        db.query(Photo).filter(Photo.entity_id == row.entity_id, Photo.status == "live").all()
    )
    for p in siblings:
        p.is_hero = p.id == row.id
        db.add(p)
    db.commit()
    return {"photo_id": row.id, "is_hero": True}


class ReorderBody(BaseModel):
    display_order: int = Field(..., ge=0, le=1_000_000)


@router.post("/api/photos/{photo_id}/reorder", status_code=200)
def reorder_photo(
    photo_id: str,
    body: ReorderBody,
    current_user: Annotated[User, Depends(require_user)],
    db: Annotated[SqlSession, Depends(get_db)],
) -> dict[str, str | int]:
    row = db.get(Photo, photo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="photo_not_found")
    if row.status != "live":
        raise HTTPException(status_code=400, detail="photo_not_live")
    if not _user_can_manage_photo(db, current_user, row):
        raise HTTPException(status_code=403, detail="forbidden")
    row.display_order = body.display_order
    db.add(row)
    db.commit()
    return {"photo_id": row.id, "display_order": row.display_order}
