from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Track A chat UI: ``session_id`` + ``message`` (POST ``/chat``)."""

    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    """Track A chat UI response shape (intent + opaque ``data``)."""

    response: str
    intent: str
    data: dict[str, Any] = Field(default_factory=dict)


class ConciergeChatRequest(BaseModel):
    """Unified router / concierge API (POST ``/api/chat`` — Phase 2.3)."""

    query: str = Field(min_length=1)
    session_id: str | None = None


class ConciergeChatResponse(BaseModel):
    """Unified router response (``app.chat.unified_router.route``)."""

    response: str
    mode: str
    sub_intent: str | None = None
    entity: str | None = None
    tier_used: str
    latency_ms: int
    llm_tokens_used: int | None = None
