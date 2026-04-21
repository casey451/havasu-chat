"""Pydantic schemas for LLM mention admin JSON API (Phase 5.5)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

MentionStatus = Literal["unreviewed", "promoted", "dismissed"]
DismissalReason = Literal[
    "already_in_catalog",
    "not_relevant",
    "noise",
    "external_reference",
    "other",
]


class LlmMentionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_log_id: str
    mentioned_name: str
    context_snippet: str | None
    detected_at: datetime
    status: str
    reviewed_at: datetime | None
    dismissal_reason: str | None
    promoted_to_contribution_id: int | None


class MentionDismissBody(BaseModel):
    reason: DismissalReason


class MentionPromoteBody(BaseModel):
    entity_type: Literal["provider", "program", "event", "tip"]
    submission_name: str = Field(min_length=1, max_length=200)
    submission_url: HttpUrl | None = None
    submission_category_hint: str | None = Field(default=None, max_length=200)
    submission_notes: str | None = None
    event_date: date | None = None
    event_time_start: time | None = None
    event_time_end: time | None = None
