from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator



ComponentType = Literal[
    "day_agenda",
    "week_strip",
    "card_row",
    "single_card",
    "single_business_card",
    "business_list",
    "none",
]


class ComponentPayload(BaseModel):
    """Structured answer-rendering payload (BUILD.md "Answer rendering contract").

    Hava's voice is one part of an answer; the rest renders as a component
    whose ``type`` tells the front-end which renderer to invoke. Loose
    schemas for each ``type`` live in BUILD.md; the front-end is the
    contract for what each renderer expects in ``data``.

    ``type="none"`` means voice-only — the voice text is the whole answer
    (greetings, no-answer responses, anything that fits in 1–3 sentences
    without a structured payload).
    """

    type: ComponentType = "none"
    data: dict[str, Any] = Field(default_factory=dict)


class ConciergeChatRequest(BaseModel):
    """Unified router / concierge API (POST ``/api/chat`` — Phase 2.3)."""

    query: str = Field(min_length=1)
    session_id: str | None = None


class ConciergeChatResponse(BaseModel):
    """Unified router response (``app.chat.unified_router.route``).

    BUILD.md step 5: the answer is split into ``voice`` (1–3 sentences in
    Hava's voice) and ``component`` (the structured renderer payload).
    ``response`` is kept as a duplicate of ``voice`` for back-compat with
    existing API consumers (the static / chat UI, anyone currently reading
    ``response: str``). New consumers should prefer ``voice`` + ``component``.
    """

    response: str  # legacy — duplicate of `voice` for back-compat
    voice: str = ""  # canonical going forward
    component: ComponentPayload = Field(default_factory=ComponentPayload)
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
