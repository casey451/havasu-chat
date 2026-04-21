"""Admin JSON API for LLM-mentioned entities (Phase 5.5)."""

from __future__ import annotations

from datetime import datetime, time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.contrib.enrichment import enrich_contribution
from app.db.contribution_store import create_contribution
from app.db.database import SessionLocal, get_db
from app.db.llm_mention_store import (
    count_mentions,
    dismiss_mention,
    get_mention,
    list_mentions,
    promote_mention,
)
from app.schemas.contribution import ContributionCreate
from app.schemas.llm_mention import (
    LlmMentionResponse,
    MentionDismissBody,
    MentionPromoteBody,
)

router = APIRouter(prefix="/admin/api", tags=["admin-mentions"])


def require_admin(request: Request) -> None:
    if not verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )


AdminAuth = Annotated[None, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_db)]


def _parse_day_bounds(
    detected_from: str | None,
    detected_to: str | None,
) -> tuple[datetime | None, datetime | None]:
    """Parse YYYY-MM-DD into naive day start/end for ``detected_at`` filtering."""
    lo: datetime | None = None
    hi: datetime | None = None
    if detected_from:
        try:
            y, m, d = (int(x) for x in detected_from.split("-", 2))
            lo = datetime(y, m, d)
        except Exception:
            raise HTTPException(status_code=422, detail="invalid detected_from (use YYYY-MM-DD)")
    if detected_to:
        try:
            y, m, d = (int(x) for x in detected_to.split("-", 2))
            hi = datetime.combine(datetime(y, m, d).date(), time(23, 59, 59))
        except Exception:
            raise HTTPException(status_code=422, detail="invalid detected_to (use YYYY-MM-DD)")
    return lo, hi


@router.get("/mentioned-entities", response_model=list[LlmMentionResponse])
def api_list_mentions(
    _: AdminAuth,
    db: DbSession,
    status_filter: str | None = Query(None, alias="status"),
    detected_from: str | None = None,
    detected_to: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[LlmMentionResponse]:
    lo, hi = _parse_day_bounds(detected_from, detected_to)
    rows = list_mentions(
        db,
        status=status_filter,
        detected_from=lo,
        detected_to=hi,
        limit=limit,
        offset=offset,
    )
    return [LlmMentionResponse.model_validate(r) for r in rows]


@router.get("/mentioned-entities/{mention_id}", response_model=LlmMentionResponse)
def api_get_mention(
    _: AdminAuth,
    db: DbSession,
    mention_id: int,
) -> LlmMentionResponse:
    row = get_mention(db, mention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return LlmMentionResponse.model_validate(row)


@router.post("/mentioned-entities/{mention_id}/dismiss", response_model=LlmMentionResponse)
def api_dismiss_mention(
    _: AdminAuth,
    db: DbSession,
    mention_id: int,
    body: MentionDismissBody,
) -> LlmMentionResponse:
    row = get_mention(db, mention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if row.status != "unreviewed":
        raise HTTPException(status_code=400, detail="Mention is not unreviewed")
    out = dismiss_mention(db, mention_id, body.reason)
    assert out is not None
    return LlmMentionResponse.model_validate(out)


@router.post("/mentioned-entities/{mention_id}/promote", response_model=LlmMentionResponse)
def api_promote_mention(
    _: AdminAuth,
    background_tasks: BackgroundTasks,
    db: DbSession,
    mention_id: int,
    body: MentionPromoteBody,
) -> LlmMentionResponse:
    row = get_mention(db, mention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if row.status != "unreviewed":
        raise HTTPException(status_code=400, detail="Mention is not unreviewed")
    if body.entity_type in ("provider", "program") and body.submission_url is None:
        raise HTTPException(status_code=422, detail="submission_url is required for provider and program")
    try:
        cdata = ContributionCreate(
            entity_type=body.entity_type,
            submission_name=body.submission_name,
            submission_url=body.submission_url,
            submission_category_hint=body.submission_category_hint,
            submission_notes=body.submission_notes,
            event_date=body.event_date,
            event_time_start=body.event_time_start,
            event_time_end=body.event_time_end,
            submitter_email=None,
            source="llm_inferred",
            llm_source_chat_log_id=row.chat_log_id,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    contrib = create_contribution(db, cdata, submitter_ip_hash=None)
    background_tasks.add_task(enrich_contribution, contrib.id, SessionLocal)
    out = promote_mention(db, mention_id, contrib.id)
    assert out is not None
    return LlmMentionResponse.model_validate(out)
