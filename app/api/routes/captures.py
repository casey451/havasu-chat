"""Screenshot capture bridge — the image inbox for the OpenClaw FB scraper.

OpenClaw (a dumb uploader) POSTs Facebook-post screenshots + metadata here; a
Cowork skill later pulls the queue, judges each shot, and marks it done.
Publishing is a *future* phase and never touches this module — this is capture
+ store + read only.

Auth reuses the machine-ingest bearer token (``require_ingest_token``, env
``INGEST_API_TOKEN``) from ``app.api.routes.ingest`` — the same door OpenClaw
already authenticates against; we deliberately do not duplicate the token logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.ingest import require_ingest_token
from app.db.database import get_db
from app.db.models import ScrapeCapture
from app.photos.r2_client import upload_bytes

router = APIRouter(prefix="/api/ingest", tags=["captures"])

IngestAuth = Annotated[None, Depends(require_ingest_token)]
DbSession = Annotated[Session, Depends(get_db)]


class CapturePatch(BaseModel):
    """Cowork marks an inbox item done and/or fixes a mislabeled name.

    Both fields are optional but at least one must be present. ``status`` only
    accepts the two forward states. ``business_name`` lets a review pass correct
    an upload filed under the wrong name (e.g. Flying X Saloon / The Office) in
    place, instead of doing DB surgery.
    """

    status: Literal["reviewed", "discarded"] | None = None
    business_name: str | None = None


def _parse_captured_at(raw: str | None) -> datetime | None:
    """Parse the optional ISO ``captured_at`` form field; 422 on malformed input."""
    if raw is None or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="captured_at must be an ISO 8601 datetime.",
        ) from exc


def _serialize(row: ScrapeCapture) -> dict:
    return {
        "id": row.id,
        "business_name": row.business_name,
        "source_url": row.source_url,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        "image_url": row.image_url,
        "notes": row.notes,
        "status": row.status,
    }


@router.post("/capture", status_code=status.HTTP_201_CREATED)
def create_capture(
    _: IngestAuth,
    db: DbSession,
    source_url: Annotated[str, Form()],
    business_name: Annotated[str | None, Form()] = None,
    captured_at: Annotated[str | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
    image: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Store one screenshot (or a metadata-only flag row).

    With an image: upload bytes to R2, store the public URL + object key, land
    the row ``new``. Without an image (OpenClaw couldn't capture): land it
    ``flagged`` so Cowork can still see the gap. Returns 201 ``{id, status,
    image_url}``.
    """
    captured_dt = _parse_captured_at(captured_at)

    image_url: str | None = None
    image_key: str | None = None
    if image is not None:
        content = image.file.read()
        if content:
            content_type = image.content_type or "image/png"
            ext = "jpg" if content_type.endswith("jpeg") else "png"
            image_key = f"scrape-captures/{uuid4()}.{ext}"
            image_url = upload_bytes(image_key, content, content_type)

    row = ScrapeCapture(
        business_name=business_name,
        source_url=source_url,
        captured_at=captured_dt,
        image_url=image_url,
        image_key=image_key,
        notes=notes,
        status="new" if image_url else "flagged",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "image_url": row.image_url}


@router.get("/captures")
def list_captures(
    _: IngestAuth,
    db: DbSession,
    capture_status: Annotated[str | None, Query(alias="status")] = "new",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict]:
    """Pull the inbox queue (newest first), optionally filtered by status."""
    stmt = select(ScrapeCapture)
    if capture_status:
        stmt = stmt.where(ScrapeCapture.status == capture_status)
    stmt = stmt.order_by(ScrapeCapture.created_at.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_serialize(r) for r in rows]


@router.patch("/captures/{capture_id}")
def update_capture(
    _: IngestAuth,
    capture_id: str,
    payload: CapturePatch,
    db: DbSession,
) -> dict:
    """Mark an inbox item ``reviewed``/``discarded`` and/or rename it. 404 if missing.

    422 if the body carries neither ``status`` nor ``business_name`` — an empty
    PATCH is almost certainly a caller mistake, not an intentional no-op.
    """
    fields = payload.model_fields_set
    if "status" not in fields and "business_name" not in fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide status and/or business_name.",
        )
    row = db.get(ScrapeCapture, capture_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Capture not found."
        )
    if "status" in fields and payload.status is not None:
        row.status = payload.status
    if "business_name" in fields:
        cleaned = (payload.business_name or "").strip()
        row.business_name = cleaned or None
    db.commit()
    db.refresh(row)
    return _serialize(row)
