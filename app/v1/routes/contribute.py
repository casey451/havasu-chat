"""POST /api/contribute* — chat contribution pipeline (master spec §4.3, §6)."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.contrib.enrichment import enrich_contribution
from app.core.background import with_retry
from app.core.rate_limit import is_rate_limit_disabled, limiter
from app.db.contribution_store import count_submissions_since_by_ip_hash, create_contribution
from app.db.database import SessionLocal, get_db
from app.db.models import ContributeFlow
from app.photos.processor import ProcessingError, decode_and_validate
from app.v1.contrib_extraction import extract_from_image_bytes, extract_from_text
from app.v1.contrib_flow import (
    apply_clarify,
    flow_response,
    flow_to_contribution_create,
    start_flow,
)

router = APIRouter()

_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "contrib_uploads"
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_MIME = frozenset({"image/jpeg", "image/png", "image/webp"})


class ContributeClarifyBody(BaseModel):
    flow_id: str
    answer: str = Field(min_length=1)


class ContributeSubmitBody(BaseModel):
    flow_id: str
    session_id: str = Field(min_length=1)


def _ip_hash(request: Request) -> str:
    ip = get_remote_address(request) or ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _rate_limited(request: Request, db: Session) -> bool:
    if is_rate_limit_disabled():
        return False
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    return count_submissions_since_by_ip_hash(db, _ip_hash(request), since) >= 5


def _save_image(content: bytes, mime: str) -> str:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if mime == "image/jpeg" else ("png" if mime == "image/png" else "webp")
    name = f"{uuid.uuid4().hex}.{ext}"
    path = _UPLOAD_DIR / name
    path.write_bytes(content)
    return f"/data/contrib_uploads/{name}"


@router.post("/api/contribute")
@limiter.limit("30/hour")
async def post_contribute_start(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """JSON or multipart start. One vision call per image."""
    ct = (request.headers.get("content-type") or "").lower()
    sid = ""
    txt: str | None = None
    upload_bytes: bytes | None = None
    upload_mime: str | None = None

    if ct.startswith("application/json"):
        data = await request.json()
        sid = str(data.get("session_id") or "").strip()
        raw_text = data.get("text")
        txt = str(raw_text).strip() if raw_text is not None else None
    else:
        form = await request.form()
        sid = str(form.get("session_id") or "").strip()
        raw_text = form.get("text")
        txt = str(raw_text).strip() if raw_text is not None else None
        upload = form.get("image")
        if upload is not None and hasattr(upload, "read"):
            upload_bytes = await upload.read()
            upload_mime = (getattr(upload, "content_type", None) or "").strip().lower()

    if not sid:
        raise HTTPException(status_code=400, detail="session_id_required")

    image_url: str | None = None
    extraction: dict | None = None
    if upload_bytes:
        if len(upload_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="image_too_large")
        mime = upload_mime or "image/jpeg"
        if mime not in _ALLOWED_MIME:
            raise HTTPException(status_code=400, detail="unsupported_image_type")
        # PERF-3 (audit :87-93): PIL decode, the disk write, and the vision LLM
        # call (45s read timeout) are sync — run them via to_thread so one flyer
        # upload can't freeze every in-flight request on the process. The
        # request's DB session has no transaction yet at this point (first use
        # is start_flow below), so no pooled connection is held across these.
        decoded = await asyncio.to_thread(decode_and_validate, upload_bytes, declared_mime=mime)
        if isinstance(decoded, ProcessingError):
            raise HTTPException(status_code=400, detail="invalid_image")
        image_url = await asyncio.to_thread(_save_image, upload_bytes, mime)
        extraction = await asyncio.to_thread(extract_from_image_bytes, upload_bytes, mime=mime)
        if not extraction and txt:
            extraction = await asyncio.to_thread(extract_from_text, txt)
    elif txt:
        extraction = await asyncio.to_thread(extract_from_text, txt)

    flow = start_flow(
        db,
        session_id=sid,
        text=txt,
        extraction=extraction,
        image_url=image_url,
    )
    return flow_response(flow)


@router.post("/api/contribute/clarify")
@limiter.limit("60/hour")
def post_contribute_clarify(
    request: Request,
    body: ContributeClarifyBody,
    db: Session = Depends(get_db),
) -> dict:
    flow = db.get(ContributeFlow, body.flow_id.strip())
    if flow is None or flow.status != "in_progress":
        raise HTTPException(status_code=404, detail="flow_not_found")
    flow = apply_clarify(db, flow, body.answer)
    return flow_response(flow)


@router.post("/api/contribute/submit")
@limiter.limit("10/hour")
def post_contribute_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ContributeSubmitBody,
    db: Session = Depends(get_db),
) -> dict:
    if _rate_limited(request, db):
        raise HTTPException(status_code=429, detail="rate_limited")
    flow = db.get(ContributeFlow, body.flow_id.strip())
    if flow is None:
        raise HTTPException(status_code=404, detail="flow_not_found")
    if flow.session_id != body.session_id.strip()[:128]:
        raise HTTPException(status_code=403, detail="session_mismatch")
    resp = flow_response(flow)
    if resp.get("next_question"):
        raise HTTPException(status_code=400, detail="flow_incomplete")
    create_body = flow_to_contribution_create(flow)
    row = create_contribution(db, create_body, submitter_ip_hash=_ip_hash(request))
    flow.status = "submitted"
    db.commit()
    background_tasks.add_task(with_retry, enrich_contribution, row.id, SessionLocal)
    return {
        "ok": True,
        "contribution_id": row.id,
        "message": "Thanks — it's in the review queue. We'll publish it after approval.",
    }
