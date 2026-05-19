"""Concierge unified-router HTTP API (Phase 2.3).

**Path (Option B, approved):** ``POST /api/chat`` — Track A's static UI still uses
``POST /chat`` with ``message`` + ``session_id``; mounting the concierge here avoids
collisions. **Intent:** keep ``/api/chat`` until Phase 3 is production-ready and the
frontend can migrate safely; then swap to unified ``POST /chat`` in a coordinated
cutover (handoff §5 Phase 2.3).

**Rate limit:** Phase 2.3 prompt cited matching ``POST /events`` (this codebase uses
``5/minute`` there); implementation uses ``120/minute`` (same as Track A ``POST /chat``).
Owner kept ``120/minute`` for conversational bursts. When a prompt gives a number and
implementation differs, flag it (anti-drift for numeric specs).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.chat import unified_router as unified
from app.contrib.mention_scanner import scan_and_save_mentions
from app.core.background import with_retry
from app.core.rate_limit import limiter
from app.core.session import get_session
from app.db.database import SessionLocal, get_db
from app.db.models import ChatLog
from app.schemas.chat import (
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatOnboardingRequest,
    ChatOnboardingResponse,
    ComponentPayload,
    ConciergeChatRequest,
    ConciergeChatResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["concierge"])


@router.post("/api/chat", response_model=ConciergeChatResponse)
# 120/min: chat bursts during back-and-forth; /events is 5/min (write spikes, not dialog).
@limiter.limit("120/minute")
def post_concierge_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: ConciergeChatRequest,
    db: Session = Depends(get_db),
) -> ConciergeChatResponse:
    """Run ``normalize → classify → …`` via :func:`unified_router.route`."""
    current_user = getattr(request.state, "current_user", None)
    preferred_mode = (
        getattr(current_user, "preferred_mode", None) if current_user is not None else None
    )
    result = unified.route(
        payload.query,
        payload.session_id,
        db,
        request_headers=dict(request.headers),
        query_params=dict(request.query_params),
        client_ip=str(request.client.host) if request.client else None,
        accept_language=request.headers.get("accept-language"),
        preferred_mode=preferred_mode,
    )
    if result.tier_used == "3" and result.chat_log_id:
        background_tasks.add_task(
            with_retry,
            scan_and_save_mentions,
            result.chat_log_id,
            result.response,
            SessionLocal,
        )
    # BUILD.md step 5: emit voice + component alongside legacy `response`.
    # `voice` defaults to `response` until handlers populate it explicitly;
    # `component` is "none" for now and lights up in steps 6+ as each query
    # shape gets its renderer.
    return ConciergeChatResponse(
        response=result.response,
        voice=result.voice or result.response,
        component=ComponentPayload(
            type=result.component_type,
            data=result.component_data,
        ),
        mode=result.mode,
        sub_intent=result.sub_intent,
        entity=result.entity,
        tier_used=result.tier_used,
        latency_ms=result.latency_ms,
        llm_tokens_used=result.llm_tokens_used,
        chat_log_id=result.chat_log_id,
    )


@router.post("/api/chat/onboarding", response_model=ChatOnboardingResponse)
@limiter.limit("120/minute")
def post_chat_onboarding(
    request: Request,
    payload: ChatOnboardingRequest,
) -> ChatOnboardingResponse:
    """Store Phase 6.3 onboarding hints on the in-memory session (quick taps)."""
    session = get_session(payload.session_id.strip())
    hints = session["onboarding_hints"]
    if payload.visitor_status is not None:
        hints["visitor_status"] = payload.visitor_status
    if payload.has_kids is not None:
        hints["has_kids"] = payload.has_kids
    logger.info(
        "chat_onboarding_hints_updated",
        extra={
            "visitor_status": hints.get("visitor_status"),
            "has_kids": hints.get("has_kids"),
        },
    )
    return ChatOnboardingResponse(
        visitor_status=hints.get("visitor_status"),
        has_kids=hints.get("has_kids"),
    )


@router.post("/api/chat/feedback", response_model=ChatFeedbackResponse)
def post_chat_feedback(
    payload: ChatFeedbackRequest,
    db: Session = Depends(get_db),
) -> ChatFeedbackResponse | JSONResponse:
    """Set ``chat_logs.feedback_signal`` for a prior concierge turn (Phase 6.2.1)."""
    row = db.get(ChatLog, payload.chat_log_id)
    if row is None:
        return JSONResponse(status_code=404, content={"error": "chat_log_id not found"})
    previous = row.feedback_signal
    row.feedback_signal = payload.signal
    db.commit()
    logger.info(
        "chat_feedback_signal_set",
        extra={
            "chat_log_id": str(row.id),
            "previous_feedback_signal": previous,
            "new_feedback_signal": payload.signal,
        },
    )
    return ChatFeedbackResponse(ok=True, chat_log_id=str(row.id), signal=payload.signal)
