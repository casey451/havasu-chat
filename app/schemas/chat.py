from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    chat_log_id: str | None = None


class ChatFeedbackRequest(BaseModel):
    """POST ``/api/chat/feedback`` — Phase 6.2.1 (public, keyed by ``chat_logs.id``)."""

    chat_log_id: str = Field(min_length=1)
    signal: Literal["positive", "negative"]


class ChatFeedbackResponse(BaseModel):
    ok: Literal[True]
    chat_log_id: str
    signal: str


class ChatOnboardingRequest(BaseModel):
    """POST ``/api/chat/onboarding`` — Phase 6.3 quick-tap hints (session memory only)."""

    session_id: str = Field(min_length=1)
    visitor_status: Literal["local", "visiting"] | None = None
    has_kids: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> ChatOnboardingRequest:
        if self.visitor_status is None and self.has_kids is None:
            raise ValueError("Provide visitor_status and/or has_kids")
        return self


class ChatOnboardingResponse(BaseModel):
    ok: Literal[True] = True
    visitor_status: Literal["local", "visiting"] | None = None
    has_kids: bool | None = None
