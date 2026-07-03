"""Operational ORM models sliced out of app/db/models.py (audit 2026-07-01
decomposition): ScrapeCapture (capture inbox), Job (admin Jobs portal work
item), LinkHealth (outbound-link sweep state).

All three are standalone tables — no relationships or FKs to other models — so
this module imports only ``Base`` (+ SQLAlchemy) and is trivially cycle-free.
``app.db.models`` re-exports them so existing imports keep resolving.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ScrapeCapture(Base):
    """Image inbox for OpenClaw Facebook-post screenshots (the capture bridge).

    OpenClaw stays dumb — it uploads a screenshot (or, when it couldn't capture,
    a metadata-only ``flagged`` row) plus the source URL here. A Cowork skill
    later pulls the queue, judges each shot, and marks it ``reviewed`` /
    ``discarded``; publishing happens in a future phase and never touches this
    table. Rows start ``new`` (image present) or ``flagged`` (no image).
    """

    __tablename__ = "scrape_captures"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'reviewed', 'discarded', 'flagged')",
            name="ck_scrape_captures_status",
        ),
        Index("ix_scrape_captures_status", "status"),
        Index("ix_scrape_captures_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    business_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="new", server_default="new"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class Job(Base):
    """Admin-queued scraper-pipeline job — the one-click Jobs portal's work item.

    Casey clicks a button in the admin Jobs page → a ``queued`` row lands here.
    Worker agents poll ``GET /api/ingest/jobs/pending?worker=...`` with the
    machine-ingest bearer token, atomically claim the oldest job matching their
    type map (OpenClaw → ``fb_capture_sweep``; Cowork → the other four), do the
    work, then PATCH the row to ``running`` / ``done`` / ``failed`` with a
    ``result_summary``. Additive + standalone — no FKs; ``params`` carries any
    per-job knobs as JSON. See docs/scraper/ADMIN_JOBS_SPEC.md.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('schedule_hunt', 'fb_capture_sweep', 'capture_review', "
            "'publish_approved', 'discovery_audit')",
            name="ck_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'claimed', 'running', 'done', 'failed')",
            name="ck_jobs_status",
        ),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_job_type", "job_type"),
        Index("ix_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued"
    )
    requested_by: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LinkHealth(Base):
    """One stored outbound URL's health, tracked across sweeps.

    Populated by ``app.monitoring.link_health`` running on the VPS. Keyed by URL
    (many rows can share one). ``consecutive_failures`` lets the sweep confirm a
    link is *really* broken across multiple runs before it surfaces, filtering
    transient blips and big-site rate-limits. Monitoring-only: nothing user-facing
    reads it, and the sweep never edits the source provider/event rows -- a dead
    link is *flagged* here for human review, not auto-removed.
    """

    __tablename__ = "link_health"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_checked_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # True once a link has failed on >= the confirm threshold consecutive sweeps.
    confirmed_broken: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    # Set true when a previously-confirmed-broken link has been emailed, so the
    # summary only ever pages once per breakage (resets when it recovers).
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Layer 2: a local-LLM read of the site's root domain for a confirmed-broken
    # link -- a short human verdict ("business still present, page moved" etc.) and
    # a suggested replacement URL, shown on the admin page to speed the fix. Never
    # auto-applied. ``llm_checked_at`` gates re-assessment so the slow model pass
    # only revisits links it hasn't judged.
    llm_assessment: Mapped[str | None] = mapped_column(String(512), nullable=True)
    llm_suggested_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    llm_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
