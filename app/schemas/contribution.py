"""Pydantic schemas for Phase 5 contributions (admin API + future user form)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

EntityType = Literal["provider", "program", "event", "tip"]
ContributionSource = Literal["user_submission", "llm_inferred", "operator_backfill"]
ContributionStatus = Literal["pending", "approved", "rejected", "needs_info"]
RejectionReason = Literal["duplicate", "out_of_area", "spam", "incomplete", "unverifiable", "other"]


class ContributionCreate(BaseModel):
    entity_type: EntityType
    submission_name: str = Field(min_length=1, max_length=200)
    submission_url: HttpUrl | None = None
    submission_category_hint: str | None = Field(default=None, max_length=200)
    submission_notes: str | None = None
    event_date: date | None = None
    event_time_start: time | None = None
    event_time_end: time | None = None
    submitter_email: EmailStr | None = None
    source: ContributionSource = "operator_backfill"
    llm_source_chat_log_id: str | None = None
    unverified: bool = False

    @model_validator(mode="after")
    def provider_requires_url(self) -> ContributionCreate:
        if self.entity_type == "provider" and self.submission_url is None:
            raise ValueError("submission_url is required when entity_type is provider")
        return self


class ContributionStatusUpdate(BaseModel):
    status: ContributionStatus
    review_notes: str | None = None
    rejection_reason: RejectionReason | None = None

    @model_validator(mode="after")
    def rejected_requires_reason(self) -> ContributionStatusUpdate:
        if self.status == "rejected" and self.rejection_reason is None:
            raise ValueError("rejection_reason is required when status is rejected")
        return self


class ContributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    submitted_at: datetime
    submitter_email: str | None
    submitter_ip_hash: str | None
    entity_type: str
    submission_name: str
    submission_url: str | None
    submission_category_hint: str | None
    submission_notes: str | None
    event_date: date | None
    event_time_start: time | None
    event_time_end: time | None
    url_title: str | None
    url_description: str | None
    url_fetch_status: str | None
    url_fetched_at: datetime | None
    google_place_id: str | None
    google_enriched_data: dict[str, Any] | list[Any] | None
    status: str
    review_notes: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_provider_id: str | None
    created_program_id: str | None
    created_event_id: str | None
    source: str
    llm_source_chat_log_id: str | None
    unverified: bool
