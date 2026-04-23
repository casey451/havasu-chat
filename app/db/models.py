from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Time, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.schemas.event import EventCreate


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    facebook: Mapped[str | None] = mapped_column(String, nullable=True)
    hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    hours_structured: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[str] = mapped_column(String, nullable=False, default="free")
    sponsored_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    featured_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pending_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_review_by: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="seed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    programs: Mapped[list["Program"]] = relationship(back_populates="provider")
    events: Mapped[list["Event"]] = relationship(back_populates="provider")


class FieldHistory(Base):
    __tablename__ = "field_history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    submitted_by_session: Mapped[str | None] = mapped_column(String, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    state: Mapped[str] = mapped_column(String, nullable=False)
    confirmations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disputes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolution_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_source: Mapped[str | None] = mapped_column(String, nullable=True)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False)
    normalized_title: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location_name: Mapped[str] = mapped_column(String, nullable=False)
    location_normalized: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="live", nullable=False)
    source: Mapped[str] = mapped_column(String, default="admin", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    created_by: Mapped[str] = mapped_column(String, default="user", nullable=False)
    admin_review_by: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id"), nullable=True
    )
    is_recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    provider: Mapped["Provider | None"] = relationship(back_populates="events")

    @classmethod
    def from_create(cls, payload: EventCreate) -> "Event":
        title = payload.title.strip()
        location_name = payload.location_name.strip()
        source = (getattr(payload, "source", None) or "admin").strip() or "admin"
        verified_in = getattr(payload, "verified", None)
        # Admin-submitted entries are auto-verified; other sources stay unverified
        # until AA-3's claim flow (or admin edit).
        verified = bool(verified_in) if verified_in is not None else source == "admin"
        return cls(
            title=title,
            normalized_title=title.lower().strip(),
            date=payload.date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            location_name=location_name,
            location_normalized=location_name.lower().strip(),
            description=payload.description.strip(),
            event_url=payload.event_url.strip(),
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            tags=payload.tags,
            embedding=payload.embedding,
            status=payload.status,
            source=source,
            verified=verified,
            created_by=payload.created_by,
            admin_review_by=payload.admin_review_by,
            is_recurring=bool(getattr(payload, "is_recurring", False)),
        )


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    # Unified router / concierge analytics (Phase 2.2+); nullable for legacy Track A rows.
    query_text_hashed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sub_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_matched: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tier_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_signal: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    activity_category: Mapped[str] = mapped_column(String, nullable=False)
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_days: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    schedule_start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    schedule_end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    location_name: Mapped[str] = mapped_column(String, nullable=False)
    location_address: Mapped[str | None] = mapped_column(String, nullable=True)
    cost: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source: Mapped[str] = mapped_column(String, default="admin", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id"), nullable=True
    )
    show_pricing_cta: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cost_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pending_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_review_by: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    provider: Mapped["Provider | None"] = relationship(back_populates="programs")


class Contribution(Base):
    """Community contribution queue (Phase 5.1)."""

    __tablename__ = "contributions"
    __table_args__ = (
        Index("ix_contributions_status", "status"),
        Index("ix_contributions_source", "source"),
        Index("ix_contributions_submitted_at", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    submitter_email: Mapped[str | None] = mapped_column(String, nullable=True)
    submitter_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    submission_name: Mapped[str] = mapped_column(String, nullable=False)
    submission_url: Mapped[str | None] = mapped_column(String, nullable=True)
    submission_category_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    submission_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_time_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    event_time_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    url_title: Mapped[str | None] = mapped_column(String, nullable=True)
    url_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_fetch_status: Mapped[str | None] = mapped_column(String, nullable=True)
    url_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    google_place_id: Mapped[str | None] = mapped_column(String, nullable=True)
    google_enriched_data: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    created_provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id"), nullable=True
    )
    created_program_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("programs.id"), nullable=True
    )
    created_event_id: Mapped[str | None] = mapped_column(String, ForeignKey("events.id"), nullable=True)

    source: Mapped[str] = mapped_column(String, nullable=False, default="user_submission")
    llm_source_chat_log_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("chat_logs.id"), nullable=True
    )
    unverified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LlmMentionedEntity(Base):
    """Tier 3 local-entity mentions for operator review (Phase 5.5)."""

    __tablename__ = "llm_mentioned_entities"
    __table_args__ = (
        UniqueConstraint("chat_log_id", "mentioned_name", name="uq_llm_mention_chat_name"),
        Index("ix_llm_mentions_detected_at", "detected_at"),
        Index("ix_llm_mentions_status", "status"),
        Index("ix_llm_mentions_chat_log_id", "chat_log_id"),
        Index("ix_llm_mentions_mentioned_name", "mentioned_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_log_id: Mapped[str] = mapped_column(String, ForeignKey("chat_logs.id"), nullable=False)
    mentioned_name: Mapped[str] = mapped_column(String(300), nullable=False)
    context_snippet: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    status: Mapped[str] = mapped_column(String, nullable=False, default="unreviewed")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    promoted_to_contribution_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contributions.id"), nullable=True
    )
