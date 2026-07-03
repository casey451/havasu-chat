from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Sliced-out ORM models (audit 2026-07-01 decomposition). Defined in their own
# modules but re-exported here so every ``from app.db.models import X`` keeps
# resolving — and so importing ``app.db.models`` registers them with ``Base``.
# Each slice module imports only ``Base`` (never ``models`` / ``entity_dual_write``),
# so these imports are cycle-free regardless of load order.
from app.db.alerts_models import (  # noqa: F401 — re-export
    AlertDispatched,
    AlertSubscription,
    DigestSubscription,
)
from app.db.auth_models import (  # noqa: F401 — re-export
    AuthSession,
    Claim,
    MagicLinkToken,
    User,
    UserFavorite,
)
from app.db.database import Base
from app.db.jobs_models import Job, LinkHealth, ScrapeCapture  # noqa: F401 — re-export
from app.db.photo_models import Photo  # noqa: F401 — re-export
from app.db.types import TZAwareDateTime
from app.schemas.event import EventCreate

# Alias for the ``Event`` table, whose ``date`` column shadows the ``date`` type
# in sibling annotations (mypy valid-type). Other models keep using ``date``.
_Date = date


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    # Indexed (audit 2026-07-01): exact-match lookups on the chat path
    # (session.record_entity) and admin/API ilike searches filter on it, and
    # slug allocation prefix-probes it; there was no index. Migration
    # aud1provname01.
    provider_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    # P0 Task 2: second-level group slug (e.g. "home-services", "dog groomer"
    # bucket). One of app/categories/subcategories.py's group slugs. Nullable —
    # rows with no classifiable Google/legacy signal stay NULL and surface under
    # the landing page's "All" chip rather than being mislabeled. Indexed for the
    # /lake-havasu/{subcategory} landing filter. Master spec §3.1.
    subcategory: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # WP-9 (audit R2): the single canonical primary category — exactly one of
    # Home's 12 slugs (app/home/queries.py CATEGORY_LABELS). Deterministically
    # derived from ``subcategory`` (then legacy ``category``) by
    # app.categories.subcategories.derive_primary_category; backfilled by
    # scripts/backfill_primary_category.py. Every public surface (Home, Explore,
    # Map, Chat, "While you're here") reads this with a legacy-category fallback
    # while NULL. Indexed for the per-primary listing/count queries. Nullable
    # until backfill; unmapped rows stay NULL (no guessed default).
    primary_category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
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
    google_photo_urls: Mapped[list[str | None] | None] = mapped_column(JSON, nullable=True)
    google_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_google_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zip: Mapped[str | None] = mapped_column(String, nullable=True)

    # Liveness ranking (2026-06-03) — bury likely-dead listings without removing
    # them. ``newest_review_at`` is the max review publishTime from the Places
    # enrichment payload (the core staleness signal). ``liveness_score`` is the
    # 0–1 blend computed by ``app/core/liveness.compute_liveness`` at load /
    # backfill time; it feeds a multiplicative rank dampener so stale rows sink
    # but are never excluded. Both nullable — non-Google rows leave them NULL,
    # which the dampener treats as 1.0 (no dampening). See the 24b922964acd
    # migration and LIVENESS_RANKING_HANDOFF_2026-06-03.md.
    newest_review_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    # Directory pivot V1 (2026-05-13): structured category FK alongside the
    # legacy string `category` column (line 36). Nullable until backfill
    # ticket lands. See docs/STRATEGY_PIVOT_2026-05-12.md §8.1.
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    # Directory pivot V1: operator-curated structured attributes (e.g. service
    # area, sub-trade, emergency-service flag). Distinct from
    # `raw_enrichment_json` which is the raw scraper dump. Nullable.
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Directory pivot V1: district label (e.g. "English Village", "Downtown")
    # for Eat & Drink category page filtering. String column rather than a
    # first-class Place row per pivot §8.2 (Place model deferred to Phase 2).
    district: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # B7 (locality): whether the provider is genuinely in the Lake Havasu service
    # area. Backfilled by scripts/backfill_is_local.py from geo distance (within
    # IN_AREA_KM of the LHC civic anchor) OR a local city token in the address —
    # local if EITHER signal says so. Nullable tri-state: NULL means "unknown"
    # (no usable geo AND no recognizable city), never assume out-of-area.
    is_local: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Directory pivot V1 follow-up (2026-05-13): URL-safe slug derived from
    # provider_name. Used as the route key for /provider/<slug>. Backfilled
    # by the f1a2b3c4d5e6 migration; new rows get a slug via the ingest
    # paths (see app/db/seed_helpers.py and scripts/ingest). Unique across
    # all providers; collision handling appends -2, -3, etc.
    slug: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True, index=True)

    last_verified_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)

    # Category patrol (2026-06-04) — a scheduled gpt-4o-mini sweep that flags
    # providers whose ``primary_category`` looks wrong (the substring-only
    # categorizer in app/categories/subcategories.py has no semantic check).
    # ``category_confidence`` is the 0-1 confidence the current category is
    # MIScategorized; ``category_flagged_at`` is set when the row is queued for
    # the admin "miscategorized?" review list and cleared on resolution. Both
    # additive + nullable; NO serving path reads them (worst-case blast radius is
    # a wrong flag, never a wrong listing). Written only by the dry-run-gated
    # scripts/category_patrol.py. See the c1d2e3f4a5b6 migration.
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    category_flagged_at: Mapped[datetime | None] = mapped_column(
        TZAwareDateTime(), nullable=True, index=True
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

    # Track B1 dedupe resolution paths (HAVA_AUDIT spec §B1; resolved via the
    # dedupe review queue in app/admin/provider_merge_review.py). Both additive
    # + nullable; see the d4e5f6a7b8c9 migration.
    #
    # ``location_group_id``: same business, multiple locations — rows sharing a
    # group id are DISTINCT listings of one business (chain/branch shape) and
    # must never be merged; profile pages cross-link the siblings. Opaque UUID
    # minted at resolve time.
    location_group_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    # ``parent_provider_id``: parent org / departments (the Specialty
    # Associates shape) — child departments point at the parent row; the parent
    # profile renders its children. Self-referential FK, no ORM relationship on
    # purpose (keeps the dual-write hooks' mapped-relationship surface
    # unchanged) — surfaces query it explicitly.
    parent_provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id"), nullable=True, index=True
    )

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id"), nullable=False, index=True
    )
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])

    programs: Mapped[list["Program"]] = relationship(back_populates="provider")
    events: Mapped[list["Event"]] = relationship(back_populates="provider")

    category_ref: Mapped["Category | None"] = relationship("Category", foreign_keys=[category_id])


class DedupeResolution(Base):
    """Persisted outcome for one reviewed duplicate-candidate pair (Track B1).

    The dedupe queue (app/admin/provider_merge_review.py) computes candidate
    pairs LIVE from current provider rows, so without persistence a reviewed
    pair reappears on every page load. One row here per resolved unordered
    pair; the queue filters resolved pairs out. Resolutions:

      * ``not_duplicate``  — distinct businesses; suppress the pair.
      * ``multi_location`` — same business, multiple locations; both rows kept
        and stamped with a shared ``Provider.location_group_id``. Never merged.
      * ``parent_child``   — parent org / department shape; the child row gets
        ``Provider.parent_provider_id`` and renders on the parent's profile.
      * ``merged``         — the pair went through ``merge_providers``; recorded
        so the (now retired) dup never resurfaces if reactivated.

    ``pair_key`` is the sorted "min_id|max_id" string — the unordered-pair
    identity — and is unique. ``reason`` snapshots the audit signal
    (phone / website / google_place_id / geo+name) at resolve time so queue
    precision is measurable later (labeled examples, HAVA_AUDIT §5.3 spirit).
    """

    __tablename__ = "dedupe_resolutions"
    __table_args__ = (
        UniqueConstraint("pair_key", name="uq_dedupe_resolutions_pair_key"),
        CheckConstraint(
            "resolution IN ('not_duplicate', 'multi_location', 'parent_child', 'merged')",
            name="ck_dedupe_resolutions_resolution",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    pair_key: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_id_a: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_id_b: Mapped[str] = mapped_column(String, nullable=False, index=True)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str] = mapped_column(String(120), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


def dedupe_pair_key(id_a: str, id_b: str) -> str:
    """Canonical unordered-pair key for ``DedupeResolution.pair_key``."""
    lo, hi = sorted((id_a, id_b))
    return f"{lo}|{hi}"


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
    date: Mapped[_Date] = mapped_column(Date, nullable=False)
    end_date: Mapped[_Date | None] = mapped_column(Date, nullable=True)
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
    # ED-3: optional event image URL (e.g. from the golakehavasu feed). Recovered
    # from a scrambled description's ``Image:`` line by the backfill, or set on
    # ingest; rendered on the event permalink when present.
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Fix 2.2 — human-readable price for the event, mirroring how ``Program.cost`` /
    # ``Program.cost_description`` model pricing. ``cost`` is a short label like
    # "$20", "Free", or "$10-$25"; ``cost_description`` holds extra pricing notes
    # ("kids under 5 free", "members $15"). Both nullable + additive; populated at
    # ingest from the source JSON-LD ``offers`` / parsed from the description, and
    # by scripts/backfill_event_fields_2026_06.py. Rendering is handled by the
    # event-detail/card lane; this lane only stores the value. See the
    # a1b2c3d4e5f7 migration.
    cost: Mapped[str | None] = mapped_column(String, nullable=True)
    cost_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fix 4.3 — instructor/host name extracted from a class title (e.g. "Tai Chi
    # Vince" -> host="Vince"). The display-grade title is cleaned by
    # app.events.title_clean (another lane); this structured field is populated at
    # ingest from the RAW title using that module's shared INSTRUCTOR_NAMES set so
    # the host survives even after the title is stripped. Nullable + additive.
    host: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="live", nullable=False)
    source: Mapped[str] = mapped_column(String, default="admin", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String, default="user", nullable=False)
    admin_review_by: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id"), nullable=True
    )
    is_recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    rrule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rdate: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    exdate: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    capacity: Mapped[int | None] = mapped_column(nullable=True)
    capacity_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # BUILD.md step 2: editorial "Hava's pick" flag. Hand-curated via DB
    # script; admin UI deferred. Distinct from spotlight placement on
    # Provider.tier / sponsored_until.
    featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id"), nullable=False, index=True
    )
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])

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
    # P2.OBS.1 — disclosure renderer telemetry (nullable when renderer did not run).
    disclosure_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    disclosure_sponsor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disclosure_tone_allowlist_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    disclosure_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Lane B-3 (cache-first observability) -- per-turn cache verdict and per-stage
    # timing breakdown. Both nullable; legacy rows remain valid.
    cache_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timing_ms: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class QueryLog(Base):
    """Privacy-friendly anonymized search intent log (master spec §3.7)."""

    __tablename__ = "query_log"
    __table_args__ = (Index("ix_query_log_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalized_intent: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Phase 2 Slice 1: which matcher layer resolved the turn (L1..L4 / a future
    # "clarify" marker, hence String(8)) and the legacy sub-intent on HTTP-layer
    # fall-through turns. Both additive + nullable (telemetry only).
    min_layer: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    sub_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class CatalogAdSlot(Base):
    """Master spec §3.8 — schema only; buying/serving deferred (table: ad_slots)."""

    __tablename__ = "ad_slots"
    __table_args__ = (
        Index("ix_ad_slots_business_id", "business_id"),
        Index("ix_ad_slots_active", "active"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    business_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id"), nullable=True
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class ContributeFlow(Base):
    """In-chat contribution clarify state (master spec §6; API §4.3)."""

    __tablename__ = "contribute_flows"
    __table_args__ = (Index("ix_contribute_flows_session_id", "session_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    contribution_type: Mapped[str] = mapped_column(String(16), nullable=False, default="event")
    payload: Mapped[dict] = mapped_column(JSON(none_as_null=True), nullable=False, default=dict)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    extraction: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


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
    # Directory pivot V1 (2026-05-13): structured category FK alongside the
    # legacy string `activity_category` column (line 267). Nullable until
    # backfill ticket lands. See docs/STRATEGY_PIVOT_2026-05-12.md §8.1.
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
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

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id"), nullable=False, index=True
    )
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])

    provider: Mapped["Provider | None"] = relationship(back_populates="programs")

    category_ref: Mapped["Category | None"] = relationship("Category", foreign_keys=[category_id])


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
    created_event_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )

    # Scraper auto-publish (schedule-hunt loop). ``confidence`` (0–1) is supplied
    # by the worker; ``target_entity_id`` names the existing venue a class schedule
    # belongs to; ``proposed_record`` carries the structured ProgramApprovalFields-
    # shaped JSON the worker extracted (validated at publish time); and
    # ``created_entity_id`` is the audit pointer for the attach-to-existing-entity
    # path (which writes Schedule/Offering rows but no Program row).
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    created_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    proposed_record: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
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

    # Phase 1 ENTITY schema (2026-05-14): discriminator for which entity_type
    # the business_id references. Null until backfill completes; backfilled
    # by the entity_schema migration to "commercial" for legacy rows (which
    # all reference Provider records). Phase 1C app-layer routing keys off
    # this column to disambiguate Provider vs Place vs Event sponsor refs.
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

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


class AnalyticsEvent(Base):
    """One row per render / click on a sponsor or chat-surface card (v54 Track B).

    Long-form sibling to the per-row ``Sponsor.impressions`` / ``Sponsor.clicks``
    counters (v52 P0). The counters answer "is this slot performing?"; this
    table answers "which slot, which rank, which surface, when?".

    ``sponsor_id`` and ``provider_id`` are SET NULL on delete so analytics
    outlives the underlying row — a sponsor takedown should not nuke the
    historical CTR data the takedown decision was based on.

    ``slot`` is sponsor inventory (``marquee`` / ``spotlight`` / ``promoted``
    / ``supporter``); ``slot_origin`` is render surface
    (``tier2_card_row`` / ``tier2_single_card``). They are intentionally
    separate columns so a future "spotlight slot rendered inside a chat
    card row" event can populate both.

    ``ranking_score`` mirrors ``Sponsor.weight`` (Integer) at emit time so
    downstream CTR-by-rank math doesn't have to re-join to a possibly-
    mutated Sponsor row. ``payload_json`` is a catch-all for fields that
    don't yet justify their own column.
    """

    __tablename__ = "analytics_events"
    # P6 perf: the admin placement/traffic dashboards group by ``slot`` and by
    # coalesce(``slot_origin``, ``slot``) over a created_at window. Without these
    # the group-by is a full scan + filesort that degrades as the table grows one
    # row per ad impression sitewide. Composite (col, created_at) so the window
    # filter rides the same index.
    __table_args__ = (
        Index("ix_analytics_events_slot_created", "slot", "created_at"),
        Index("ix_analytics_events_slot_origin_created", "slot_origin", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    event_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    slot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sponsor_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("sponsors.id", ondelete="SET NULL"), nullable=True
    )
    provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    ranking_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slot_origin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False, index=True
    )


class Feedback(Base):
    """User-submitted feedback / "report wrong or missing info" (P5, §2.4).

    The source of truth for the feedback channel: every submission writes a row
    here first (so it's never lost), then fires one Resend notification to the
    operator. This kills the old mailto black hole + the phantom "feedback
    button" privacy/terms referenced.

    Anonymized like ``QueryLog`` — we keep an optional reply ``email`` only when
    the user supplies one; no IP / user-agent / user-id is persisted (rate
    limiting hashes the IP in memory, never to a row).
    """

    __tablename__ = "feedback"
    __table_args__ = (
        Index("ix_feedback_status", "status"),
        Index("ix_feedback_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # The entry point sets this: 'wrong_info' | 'missing_info' | 'general' | 'bug'.
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    # What the report is about, when it came from a listing/category/event page:
    # target_type in {'provider','category','event','page'}; target_ref is the
    # slug/id/name the control prefilled.
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Moderation lifecycle: 'new' | 'reviewed' | 'resolved' | 'spam'.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Category(Base):
    """Directory taxonomy — V1 cut of 12 canonical categories.

    Locked 2026-05-13 per docs/STRATEGY_PIVOT_2026-05-12.md §8.1. Coexists
    with the legacy free-text Provider.category and Program.activity_category
    string columns; backfill and deprecation are deferred to future tickets.
    The 12 seed rows are inserted by the directory_v1_schema Alembic
    migration; `slug` is the stable identifier for application code.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # A.3 taxonomy tree (docs/proposals/A3-apply-spec.md): departments are
    # level 0 with parent_id NULL; leaves are level 1 with parent_id = dept id.
    # The flat 12-row V1 cut is level 0 / parent NULL, so it stays valid until
    # scripts/seed_taxonomy.py fills the full 15-dept / 126-leaf tree.
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    level: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    parent: Mapped["Category | None"] = relationship(
        "Category", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(
        "Category", back_populates="parent", order_by="Category.sort_order"
    )


class Entity(Base):
    """Unified core entity table — one row per directory thing.

    Replaces the parallel Provider/Event/Program/Place top-level tables with
    a single core + discriminator. Existing top-level tables remain during
    transition (Phase 1B backfills them into entities; Phase 1C pivots app
    reads to entities; Phase 1D pivots writes to dual-target; legacy table
    drops are deferred to V1.5+/Phase 13 per master plan).

    See docs/maintainability/master_build_plan.md §4 Phase 1.
    """

    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint(
            "heat_exposure IS NULL OR heat_exposure IN ("
            "'indoor', 'shaded', 'outdoor', 'water_adjacent'"
            ")",
            name="ck_entities_heat_exposure",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="seed")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Phase 3.1 — Opus v1.1 operator-curated fields (see Phase 3 brief §4.1).
    heat_exposure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crowd_notes: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    is_mobile_service: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    boat_access: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    seasonal_hours: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    district_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("districts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(), index=True
    )

    # Liveness ranking (2026-06-03) — forward-compat mirror of
    # ``Provider.liveness_score`` on the unified entity. Synced from the legacy
    # Provider row by the dual-write hooks; NULL for non-Google / non-commercial
    # entities (the rank dampener treats NULL as 1.0). See the 24b922964acd
    # migration and LIVENESS_RANKING_HANDOFF_2026-06-03.md.
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # WP-9 (audit R2): forward-compat mirror of ``Provider.primary_category`` on
    # the unified entity (one of Home's 12 canonical slugs). NULL for non-Google /
    # non-commercial entities and until the backfill syncs it. See the
    # d7e8f9a0b1c2 migration.
    primary_category: Mapped[str | None] = mapped_column(String, nullable=True)

    categories: Mapped[list["EntityCategory"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    location: Mapped["Location | None"] = relationship(
        back_populates="entity", uselist=False, passive_deletes=True
    )
    hours: Mapped[list["Hours"]] = relationship(back_populates="entity", passive_deletes=True)
    seasonal_hour_rows: Mapped[list["SeasonalHours"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    contact_points: Mapped[list["ContactPoint"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    features: Mapped[list["Feature"]] = relationship(back_populates="entity", passive_deletes=True)
    offerings: Mapped[list["Offering"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    service_areas: Mapped[list["ServiceArea"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    source_evidence: Mapped[list["SourceEvidence"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    sponsorship_slots: Mapped[list["SponsorshipSlot"]] = relationship(
        back_populates="entity", passive_deletes=True
    )
    photos: Mapped[list["Photo"]] = relationship(
        "Photo",
        primaryjoin="and_(Photo.entity_id == Entity.id, Photo.status == 'live')",
        viewonly=True,
        order_by="Photo.display_order",
    )
    district: Mapped["District | None"] = relationship(
        "District", back_populates="entities", foreign_keys=[district_id]
    )


class EntityCategory(Base):
    """M:M link between Entity and Category (Tier 1/2/3 taxonomy)."""

    __tablename__ = "entity_categories"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "category_id",
            name="uq_entity_categories_entity_category",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=False, index=True
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="categories")
    category: Mapped["Category"] = relationship("Category", foreign_keys=[category_id])


class Location(Base):
    """Structured address + geo for an entity (1:1 with Entity)."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("entity_id", name="uq_locations_entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str | None] = mapped_column(String(8), nullable=True)
    zip: Mapped[str | None] = mapped_column(String(16), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    google_place_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship(back_populates="location")


class Hours(Base):
    """Weekly hours row (1:N); one row per weekday slice."""

    __tablename__ = "hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    closes_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_24h: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="hours")


class SeasonalHours(Base):
    """Seasonal operating windows with structured hours overlay (JSON)."""

    __tablename__ = "seasonal_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season: Mapped[str] = mapped_column(String(16), nullable=False)
    applies_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    applies_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    hours_overlay: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="seasonal_hour_rows")


class ContactPoint(Base):
    """Phone, email, web, social handles for an entity."""

    __tablename__ = "contact_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="contact_points")


class Feature(Base):
    """Boolean / enum-shaped feature flags (heat_exposure, boat_access, …)."""

    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("entity_id", "key", name="uq_features_entity_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="features")


class Offering(Base):
    """Services, menu items, or program offerings."""

    __tablename__ = "offerings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_min_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_max_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship(back_populates="offerings")


class ServiceArea(Base):
    """Mobile service coverage zones."""

    __tablename__ = "service_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(32), nullable=False)
    radius_miles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="service_areas")


class Schedule(Base):
    """Event/program/recurring schedules."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    days_of_week: Mapped[list | None] = mapped_column(JSON, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship(back_populates="schedules")


class SourceEvidence(Base):
    """Per-field provenance for ENTITY rows."""

    __tablename__ = "source_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_path: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="source_evidence")


class SponsorshipSlot(Base):
    """Links an entity to sponsor inventory."""

    __tablename__ = "sponsorship_slots"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "sponsor_id",
            "slot_type",
            name="uq_sponsorship_slots_entity_sponsor_slot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sponsor_id: Mapped[str] = mapped_column(
        String, ForeignKey("sponsors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    entity: Mapped["Entity"] = relationship(back_populates="sponsorship_slots")


def _register_provider_slug_listeners() -> None:
    from app.db.seed_helpers import register_provider_slug_hooks

    register_provider_slug_hooks()


class District(Base):
    """Geographic / narrative district for profile context (Phase 3.1)."""

    __tablename__ = "districts"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_districts_slug"),
        Index("ix_districts_display_order", "display_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    paragraph: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    entities: Mapped[list["Entity"]] = relationship(
        "Entity", back_populates="district", foreign_keys="Entity.district_id"
    )


class ExternalConditionsCache(Base):
    """Keyed cache row per upstream conditions source (Phase 3.1)."""

    __tablename__ = "external_conditions_cache"
    __table_args__ = (
        Index("ix_external_conditions_cache_fetched_at", "fetched_at"),
        Index("ix_external_conditions_cache_next_attempt_after", "next_attempt_after"),
    )

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_attempt_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PeerRecommendation(Base):
    """Peer-to-peer place notes; V1.5-gated writes (Phase 3.1 schema only)."""

    __tablename__ = "peer_recommendations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'published', 'rejected')",
            name="ck_peer_recommendations_status",
        ),
        UniqueConstraint(
            "recommender_user_id",
            "entity_id",
            name="uq_peer_recommendations_recommender_entity",
        ),
        Index("ix_peer_recommendations_entity_id_status", "entity_id", "status"),
        Index("ix_peer_recommendations_recommender_user_id", "recommender_user_id"),
        Index("ix_peer_recommendations_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recommender_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_text: Mapped[str] = mapped_column("text", String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    recommender: Mapped["User"] = relationship(
        "User", back_populates="peer_recommendations", foreign_keys=[recommender_user_id]
    )
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])


class Outbox(Base):
    """Must-not-lose background-job row (Phase 4.1).

    Each row represents one queued unit of work that the application
    must eventually deliver — the canonical V1 consumer is the
    magic-link send (silently dropping it costs a user signup). See
    :mod:`app.core.background` for the state-machine semantics and
    ``docs/maintainability/background_job_infrastructure_decision.md`` §6.2
    for the design rationale.

    NO module-import-time hook registration belongs on this class —
    gotcha #17 cure. If session-level semantics are needed in the
    future, the registration lives in ``app/db/__init__.py``, not here
    and not in :mod:`app.core.background` (which is itself careful to
    lazy-import this class via function-scope imports).
    """

    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('magic_link', 'sponsor_notification', 'image_processing', 'other')",
            name="ck_outbox_kind",
        ),
        CheckConstraint(
            "state IN ('pending', 'in_flight', 'delivered', 'failed')",
            name="ck_outbox_state",
        ),
        Index("ix_outbox_state_created_at", "state", "created_at"),
        Index("ix_outbox_kind", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
        server_default=func.now(),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UpgradeRequestStatus(str, Enum):
    """Lifecycle of a merchant's request to feature/spotlight their listing.

    ``pending`` — submitted by a verified owner, awaiting admin review.
    ``approved`` — admin accepted; an admin may have spawned a live Sponsor row.
    ``declined`` — admin rejected (with an optional reason).

    No payment/billing state lives here — pricing and what-is-sold is a Casey
    product decision (Phase A4 FLAG). The request is purely a queued lead.
    """

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class UpgradeRequest(Base):
    """Merchant-initiated request to upgrade a claimed listing to a paid ad slot.

    Captures intent only: a verified owner of an Entity (commercial/place) asks
    to have their listing featured in a sponsor slot (marquee/spotlight/
    promoted/supporter). An admin reviews the queue and, on approval, can create
    a live :class:`Sponsor` row from the request. NO billing — pricing and
    free-vs-paid is deferred to Casey.

    ``entity_id`` mirrors the :class:`Claim` linkage (the owner edits a listing
    via a verified claim on the same entity). ``business_id`` is an optional
    Provider id snapshot so the admin queue can deep-link without re-resolving
    the entity. ``requested_slot`` is the desired :class:`AdSlot`.
    """

    __tablename__ = "upgrade_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'declined')",
            name="ck_upgrade_requests_status",
        ),
        Index("ix_upgrade_requests_status", "status"),
        Index("ix_upgrade_requests_entity_id", "entity_id"),
        Index("ix_upgrade_requests_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Default is PROMOTED (a slot with a live v4 render surface). Was SPOTLIGHT
    # until 2026-07-03, when the Featured/spotlight tier was retired from sellable
    # inventory — it has no v4 surface, so it can no longer be requested.
    # App-layer default only (no server_default), so this is a code change with
    # no migration; existing rows keep their stored value.
    requested_slot: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AdSlot.PROMOTED.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=UpgradeRequestStatus.PENDING.value
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when an admin spins a live Sponsor row out of this request.
    created_sponsor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])


class AdReservationStatus(str, Enum):
    """Lifecycle of a prospect's manual-invoice ad-placement reservation.

    ``pending`` — the prospect submitted the /portal/reserve form; awaiting
    operator follow-up.
    ``contacted`` — the operator has reached out to confirm + invoice.
    ``closed`` — the deal closed (invoice sent/paid offline).
    ``declined`` — the prospect or operator dropped the reservation.

    NO payment/billing state lives here. The reservation is a captured lead;
    Casey closes by invoice offline (see PR FLAG — no payment processing).
    """

    PENDING = "pending"
    CONTACTED = "contacted"
    CLOSED = "closed"
    DECLINED = "declined"


class AdReservation(Base):
    """A prospect's "reserve this spot" request from /portal/advertise.

    The keystone of the manual-invoice monetization flow: a prospect clicks
    "Reserve this spot" on an ad product, fills a short form, and a server-side
    reservation lands here while the operator is notified. NO payment is taken
    — Casey closes the deal by invoice offline. The product name/price snapshot
    is captured at reserve time so the queue reads correctly even if the catalog
    later changes.

    ``product_key`` is the catalog key (e.g. ``"category"``/``"founding"``).
    ``category_or_notes`` carries the chosen category for category sponsorships,
    or freeform notes for everything else.
    """

    __tablename__ = "ad_reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'contacted', 'closed', 'declined')",
            name="ck_ad_reservations_status",
        ),
        Index("ix_ad_reservations_status", "status"),
        Index("ix_ad_reservations_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    product_key: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    business_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_email: Mapped[str] = mapped_column(String, nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    category_or_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AdReservationStatus.PENDING.value,
        server_default="pending",
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="advertise_page", server_default="advertise_page"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class MovieShowtime(Base):
    """A single movie showtime at a local theater (the /movies surface).

    Dedicated table so high-volume, churning showtimes stay OUT of the shared
    events pipeline entirely: they can't leak into the general events feed and
    they skip the contributions/auto-approve gate. One denormalized row per
    showing (volume is small, ~250 rows). Idempotent on
    ``(source, source_stable_id)`` — re-scrapes upsert. Standalone, no FKs, and
    NOT promoted to ``entities`` (the Phase 1D dual-write hook only handles
    Provider/Event/Program).
    """

    __tablename__ = "movie_showtimes"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_stable_id", name="uq_movie_showtimes_source_stable"
        ),
        Index("ix_movie_showtimes_show_date", "show_date"),
        Index("ix_movie_showtimes_theater_slug", "theater_slug"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_stable_id: Mapped[str] = mapped_column(String(128), nullable=False)
    theater_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    theater_name: Mapped[str] = mapped_column(String(120), nullable=False)
    film_title: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    director: Mapped[str | None] = mapped_column(String(255), nullable=True)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    screen: Mapped[str | None] = mapped_column(String(64), nullable=True)
    show_date: Mapped[_Date] = mapped_column(Date, nullable=False)
    show_time: Mapped[time] = mapped_column(Time, nullable=False)
    booking_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_sold_out: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_free: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    scraped_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)


# Phase 4.1 ships the ``Outbox`` ORM class above this line. The provider-slug
# listener registration below remains the canonical "leaf-module hook"
# pattern for this codebase (not to be confused with the Phase 1D dual-write
# hook in ``app/db/__init__.py`` — gotcha #17 governs *that* one).
_register_provider_slug_listeners()
