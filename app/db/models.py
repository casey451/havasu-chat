from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import TZAwareDateTime
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

    google_place_id: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    enrichment_version: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_enrichment_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Google Places (New) columns — Phase 5 of the LHC business pull. See
    # relay/HAVA_GOOGLE_BUSINESSES_HANDOFF_2026-05-06.md §8 and the
    # e9f0a1b2c3d4 migration. `google_place_id IS NOT NULL` distinguishes
    # rows sourced from the Places pull from event/program providers. The
    # plain index on google_place_id is replaced by a partial unique index
    # in the same migration.
    google_primary_category: Mapped[str | None] = mapped_column(String, nullable=True)
    google_categories: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    google_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    google_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    google_review_snippets: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    google_photo_refs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    google_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_google_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zip: Mapped[str | None] = mapped_column(String, nullable=True)

    last_verified_at: Mapped[datetime | None] = mapped_column(
        TZAwareDateTime(), nullable=True
    )
    # CHECK ck_providers_verification_method — nullable string; allowed values are
    # NULL or one of: manual, scraper, owner_confirmed, npi_registry, none,
    # phone_call, in_person, web_form_submission, email_confirmation (see migration
    # c5d6e7f8a9b0; legacy five values predate operator enrichment CSV vocab).
    verification_method: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # BUILD.md step 2: editorial "Hava's pick" flag. Hand-curated via DB
    # script; admin UI deferred. Distinct from spotlight placement on
    # Provider.tier / sponsored_until.
    featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
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
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location_name: Mapped[str] = mapped_column(String, nullable=False)
    location_normalized: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
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
    # BUILD.md step 2: editorial "Hava's pick" flag. Hand-curated via DB
    # script; admin UI deferred. Distinct from spotlight placement on
    # Provider.tier / sponsored_until.
    featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        TZAwareDateTime(), nullable=True
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
            end_date=payload.end_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            location_name=location_name,
            location_normalized=location_name.lower().strip(),
            description=payload.description.strip(),
            event_url=payload.event_url.strip(),
            source_url=getattr(payload, "source_url", None),
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
    audience_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    activity_category: Mapped[str] = mapped_column(String, nullable=False)
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_days: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Slice 56 (Backlog #30 close): canonical schedule columns are typed Time.
    # The campaign's transient String(5) source columns and `*_typed` shadow
    # columns are dropped and renamed (respectively) by the Slice 56 migration;
    # ProgramCreate's @field_validator(mode='before') parses HH:MM strings from
    # API/form callers into time objects at the schema boundary.
    schedule_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    schedule_end_time: Mapped[time] = mapped_column(Time, nullable=False)
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

    # BUILD.md step 2: editorial "Hava's pick" flag. Hand-curated via DB
    # script; admin UI deferred. Distinct from spotlight placement on
    # Provider.tier / sponsored_until.
    featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

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
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    submission_category_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    submission_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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


class LlmResponseCache(Base):
    """Tier 3 (and optionally Tier 2 LLM) response cache.

    Stream C, lever Cache (2026-05-08): caches assistant text keyed by
    ``(normalized_query, context_hash, rubric_version)`` so identical or
    similar synthesis queries don't re-spend tokens. The rubric_version is a
    short hash of the prompts files; when any prompt content changes, the
    version bumps and stale entries are filtered out on lookup. TTL is per
    entry — null = no expiry; caller chooses based on query shape (event
    listings short, evergreen recommendations longer).

    Hits bump ``hit_count`` and ``last_hit_at`` for observability. Misses
    fall through to the live LLM call which writes the response back into
    the cache. Expired entries are treated as misses and overwritten.
    """

    __tablename__ = "llm_response_cache"
    __table_args__ = (
        Index("ix_llm_response_cache_cache_key", "cache_key", unique=True),
        Index("ix_llm_response_cache_rubric_version", "rubric_version"),
        Index("ix_llm_response_cache_ttl_until", "ttl_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(500), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(32), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    tier_used: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ttl_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # §4.3 (cache v2): JSON-encoded list[float] of the query embedding produced
    # by OpenAI text-embedding-3-small at store() time. Nullable because pre-v2
    # entries (and any rows where the embedding API call failed) won't have
    # one — those rows still serve exact-match hits and are simply skipped
    # during the similarity scan. Stored as TEXT for SQLite/Postgres parity;
    # not indexed (sequential scan is fine while the cache is small).
    query_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)


class AdSlot(str, Enum):
    """Four-tier ad inventory slots (CRITIQUE_AND_REDESIGN.md §B5.6).

    Stored as plain string in the ``sponsors.slot`` column — Postgres ENUM types
    are avoided here so adding a new tier in code doesn't require an Alembic
    migration. The ``slot`` column has CHECK validation in app code, not at the
    DB level.
    """

    MARQUEE = "marquee"
    SPOTLIGHT = "spotlight"
    PROMOTED = "promoted"
    SUPPORTER = "supporter"


class SponsorStatus(str, Enum):
    """Moderation pipeline state machine (CRITIQUE_AND_REDESIGN.md §B5.6).

    Transitions:
      draft     → review     (advertiser submits)
      review    → approved   (admin reviews + approves)
      review    → draft      (admin rejects with comment)
      approved  → live       (auto when start_date ≤ today ≤ end_date)
      live      → paused     (admin emergency takedown)
      paused    → live       (admin resume)
      live      → archived   (auto when today > end_date)
      approved  → archived   (auto if approved but never reached its window)
    """

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    LIVE = "live"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Sponsor(Base):
    """Sponsor record — backs all four ad inventory tiers.

    Phase 2B (CRITIQUE_AND_REDESIGN.md §B5.6) evolved this from the original
    single-slot editorial banner into a four-tier model (Marquee / Spotlight /
    Promoted / Supporter) with a draft → review → approved → live → paused →
    archived state machine. Existing rows from the pre-Phase-2B era are
    defaulted to ``slot='marquee'`` and ``status='approved'`` by the migration
    so they continue to render in the old slot.

    Active-record query: ``slot == X AND status == APPROVED AND active is True
    AND starts_at <= now AND (ends_at is null OR ends_at > now)``. The legacy
    ``active`` boolean is retained as an admin kill-switch that bypasses the
    state machine for emergency takedowns; ``status='paused'`` is the
    state-machine-tracked equivalent.
    """

    __tablename__ = "sponsors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    # Inventory + lifecycle
    slot: Mapped[str] = mapped_column(String(32), nullable=False, default=AdSlot.MARQUEE.value)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SponsorStatus.DRAFT.value
    )

    # Advertiser-supplied copy + assets
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pitch: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribution_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_fields_present: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    eyebrow: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta_label: Mapped[str] = mapped_column(String(64), nullable=False, default="Visit")
    cta_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Optional reference to a Provider id for in-catalog advertisers; null for
    # external. No DB-level FK — see migration 2a3b4c5d6e7f docstring for why.
    # Validation/integrity is enforced in app layer (sponsor_store + admin UI).
    business_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Booking window
    starts_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)

    # Admin kill-switch (back-compat — bypass FSM for emergency takedown)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Higher weight wins when multiple sponsors are simultaneously active in same slot.
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Moderation trail
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Performance counters
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Bookkeeping
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
