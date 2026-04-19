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

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.chat import unified_router as unified
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.schemas.chat import ConciergeChatRequest, ConciergeChatResponse

router = APIRouter(tags=["concierge"])


@router.post("/api/chat", response_model=ConciergeChatResponse)
# 120/min: chat bursts during back-and-forth; /events is 5/min (write spikes, not dialog).
@limiter.limit("120/minute")
def post_concierge_chat(
    request: Request,
    payload: ConciergeChatRequest,
    db: Session = Depends(get_db),
) -> ConciergeChatResponse:
    """Run ``normalize → classify → …`` via :func:`unified_router.route`."""
    result = unified.route(payload.query, payload.session_id, db)
    return ConciergeChatResponse(
        response=result.response,
        mode=result.mode,
        sub_intent=result.sub_intent,
        entity=result.entity,
        tier_used=result.tier_used,
        latency_ms=result.latency_ms,
    )
