"""Attach master-spec contribution flow to chat responses."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.chat.unified_router import ChatResponse
from app.schemas.chat import ComponentPayload
from app.v1.contrib_flow import flow_response, start_flow


def contribute_component_for_chat(
    db: Session,
    *,
    session_id: str,
    query_text: str,
) -> tuple[str, ComponentPayload]:
    """Start or refresh a contribute flow; return voice line + component."""
    flow = start_flow(
        db,
        session_id=session_id[:128],
        text=query_text,
        extraction=None,
        image_url=None,
    )
    data = flow_response(flow)
    voice = "Got it — I'll walk you through what to add. " + (
        data.get("next_question") or "Review the summary below, then send it for review."
    )
    if data.get("status") == "ready":
        voice = "Here's what I'll send for review. Tap Submit when it looks right."
    return voice, ComponentPayload(type="contribute_flow", data=data)


def maybe_enrich_contribute_response(
    db: Session,
    *,
    session_id: str | None,
    query_text: str,
    result: ChatResponse,
) -> tuple[str, ComponentPayload]:
    """When router mode is contribute, replace placeholder voice with live flow."""
    sid = (session_id or "").strip() or "anonymous"
    voice, component = contribute_component_for_chat(db, session_id=sid, query_text=query_text)
    return voice, component
