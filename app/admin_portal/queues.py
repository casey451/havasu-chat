"""Pending-work counts shared by the dashboard and moderation hub.

Each entry deep-links to the EXISTING admin screen that handles the
queue — the portal is a front door, not a rewrite of working pages.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.provider_approval import pending_provider_count
from app.admin.provider_merge_review import duplicate_pair_count
from app.admin_portal.address_quality import address_flag_count
from app.db.models import (
    AdReservation,
    Claim,
    Contribution,
    Event,
    ScrapeCapture,
    UpgradeRequest,
)


@dataclass(frozen=True)
class QueueCard:
    key: str
    label: str
    count: int
    href: str
    blurb: str


def _count(db: Session, stmt) -> int:
    return int(db.execute(stmt).scalar() or 0)


def queue_cards(db: Session) -> list[QueueCard]:
    """All review queues with live counts, ordered by urgency convention."""
    cards = [
        QueueCard(
            "providers",
            "Providers pending",
            pending_provider_count(db),
            "/admin/providers/pending",
            "New/draft providers awaiting approval",
        ),
        QueueCard(
            "events",
            "Events pending",
            _count(
                db,
                select(func.count()).select_from(Event).where(Event.status == "pending_review"),
            ),
            "/admin?tab=queue",
            "Scraped/submitted events awaiting review",
        ),
        QueueCard(
            "claims",
            "Claims pending",
            _count(
                db, select(func.count()).select_from(Claim).where(Claim.status == "pending")
            ),
            "/admin/claims",
            "Business-owner claims to verify",
        ),
        QueueCard(
            "contributions",
            "Contributions pending",
            _count(
                db,
                select(func.count())
                .select_from(Contribution)
                .where(Contribution.status == "pending"),
            ),
            "/admin/contributions",
            "Public submissions to triage",
        ),
        QueueCard(
            "duplicates",
            "Duplicate pairs",
            duplicate_pair_count(db),
            "/admin/providers/duplicates",
            "Provider merge candidates",
        ),
        QueueCard(
            "addresses",
            "Address flags",
            address_flag_count(db),
            "/admin/portal/addresses",
            "WS-4 pattern checks (review, never auto-fix)",
        ),
        QueueCard(
            "upgrades",
            "Upgrade requests",
            _count(
                db,
                select(func.count())
                .select_from(UpgradeRequest)
                .where(UpgradeRequest.status == "pending"),
            ),
            "/admin/upgrade-requests",
            "Sponsor/tier upgrade asks",
        ),
        QueueCard(
            "ads",
            "Ad reservations",
            _count(
                db,
                select(func.count())
                .select_from(AdReservation)
                .where(AdReservation.status == "pending"),
            ),
            "/admin/ad-reservations",
            "Reserved slots awaiting contact",
        ),
        QueueCard(
            "captures",
            "Capture inbox",
            _count(
                db,
                select(func.count())
                .select_from(ScrapeCapture)
                .where(ScrapeCapture.status.in_(("new", "flagged"))),
            ),
            "/admin/jobs",
            "OpenClaw screenshots to judge",
        ),
    ]
    return cards
