"""Tests for ``app.contrib.approval_service`` (Phase 5.3)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.contrib.approval_service import (
    approve_contribution_as_event,
    approve_contribution_as_program,
    approve_contribution_as_provider,
    enrichment_suggests_verified,
)
from app.db.contribution_store import create_contribution
from app.db.database import SessionLocal
from app.db.models import Contribution, Event, Program, Provider
from app.schemas.contribution import ContributionCreate, EventApprovalFields, ProgramApprovalFields, ProviderApprovalFields


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _provider_contribution(db: Session) -> Contribution:
    u = uuid.uuid4().hex[:8]
    return create_contribution(
        db,
        ContributionCreate(
            entity_type="provider",
            submission_name=f"Svc Gym {u}",
            submission_url=f"https://example.com/gym-{u}",
            source="operator_backfill",
        ),
        submitter_ip_hash=None,
    )


def _program_contribution(db: Session) -> Contribution:
    u = uuid.uuid4().hex[:8]
    return create_contribution(
        db,
        ContributionCreate(
            entity_type="program",
            submission_name=f"Svc Program {u}",
            submission_notes="A" * 25,
            source="operator_backfill",
        ),
        submitter_ip_hash=None,
    )


def _event_contribution(db: Session) -> Contribution:
    u = uuid.uuid4().hex[:8]
    from datetime import date, time

    return create_contribution(
        db,
        ContributionCreate(
            entity_type="event",
            submission_name=f"Svc Event {u}",
            submission_notes="B" * 22,
            submission_url=f"https://example.com/ev-{u}",
            event_date=date(2026, 6, 15),
            event_time_start=time(14, 30),
            event_time_end=time(16, 0),
            source="operator_backfill",
        ),
        submitter_ip_hash=None,
    )


def test_approve_provider_sets_catalog_and_contribution(db: Session) -> None:
    c = _provider_contribution(db)
    cid = c.id
    fields = ProviderApprovalFields(
        name="Approved Gym X",
        address="1 Main St",
        phone=None,
        hours="Mon 9-5",
        description="A fine gym for testing approval flow.",
        website="https://approved.example",
    )
    p = approve_contribution_as_provider(db, cid, fields, "swim")
    assert p.provider_name == "Approved Gym X"
    assert p.category == "swim"
    assert p.is_active is True
    assert p.draft is False
    c2 = db.get(Contribution, cid)
    assert c2 is not None
    assert c2.status == "approved"
    assert c2.created_provider_id == p.id


def test_approve_program(db: Session) -> None:
    c = _program_contribution(db)
    cid = c.id
    pr = ProgramApprovalFields(
        title="Youth Swim Lessons",
        description="Twenty chars minimum here.",
        age_min=5,
        age_max=12,
        schedule_days=["monday", "wednesday"],
        schedule_start_time="09:00",
        schedule_end_time="10:00",
        location_name="City Pool",
        location_address="Pool Rd",
        cost="$50",
        provider_name="City Aquatics",
        contact_phone=None,
        contact_email=None,
        contact_url=None,
        tags=["summer"],
    )
    prog = approve_contribution_as_program(db, cid, pr, "swim")
    assert prog.title == "Youth Swim Lessons"
    assert prog.activity_category == "swim"
    c2 = db.get(Contribution, cid)
    assert c2 is not None
    assert c2.status == "approved"
    assert c2.created_program_id == prog.id


def test_approve_event(db: Session) -> None:
    c = _event_contribution(db)
    cid = c.id
    from datetime import date, time

    evf = EventApprovalFields(
        title="Summer Kickoff Fair",
        description="Community event description text.",
        date=date(2026, 7, 4),
        start_time=time(10, 0),
        end_time=time(12, 0),
        location_name="London Bridge Beach",
        event_url="https://example.com/event-page",
    )
    ev = approve_contribution_as_event(db, cid, evf, ["family", "free"])
    assert ev.title == "Summer Kickoff Fair"
    assert "family" in ev.tags
    c2 = db.get(Contribution, cid)
    assert c2 is not None
    assert c2.status == "approved"
    assert c2.created_event_id == ev.id


def test_approve_non_pending_raises(db: Session) -> None:
    c = _provider_contribution(db)
    approve_contribution_as_provider(
        db,
        c.id,
        ProviderApprovalFields(
            name="Once",
            description="Enough text here for provider desc field optional.",
            website="https://x.example",
        ),
        "sports",
    )
    with pytest.raises(ValueError, match="not pending"):
        approve_contribution_as_provider(
            db,
            c.id,
            ProviderApprovalFields(
                name="Twice",
                description="Enough text here for provider desc field optional.",
                website="https://y.example",
            ),
            "sports",
        )


def test_approve_missing_category_raises(db: Session) -> None:
    c = _provider_contribution(db)
    with pytest.raises(ValueError, match="category"):
        approve_contribution_as_provider(
            db,
            c.id,
            ProviderApprovalFields(
                name="Z",
                description="Desc here for provider optional long enough.",
                website="https://z.example",
            ),
            "   ",
        )


def test_approve_not_found_raises(db: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        approve_contribution_as_provider(
            db,
            999_999_999,
            ProviderApprovalFields(
                name="Nope",
                description="Enough text here for provider desc field optional.",
                website="https://n.example",
            ),
            "swim",
        )


def test_rollback_when_commit_fails(db: Session) -> None:
    c = _provider_contribution(db)
    cid = c.id
    fields = ProviderApprovalFields(
        name="Rollback Gym",
        description="Enough text here for provider desc field optional.",
        website="https://rollback.example",
    )
    with patch.object(db, "commit", side_effect=RuntimeError("simulated")):
        with pytest.raises(RuntimeError, match="simulated"):
            approve_contribution_as_provider(db, cid, fields, "swim")
    db2 = SessionLocal()
    try:
        c2 = db2.get(Contribution, cid)
        assert c2 is not None
        assert c2.status == "pending"
        assert db2.query(Provider).filter(Provider.provider_name == "Rollback Gym").count() == 0
    finally:
        db2.close()


def test_verified_true_when_url_fetch_success(db: Session) -> None:
    c = _provider_contribution(db)
    c.url_fetch_status = "success"
    db.add(c)
    db.commit()
    p = approve_contribution_as_provider(
        db,
        c.id,
        ProviderApprovalFields(
            name="Verified URL Gym",
            description="Enough text here for provider desc field optional.",
            website="https://vu.example",
        ),
        "swim",
    )
    assert p.verified is True


def test_verified_true_when_places_success(db: Session) -> None:
    c = _provider_contribution(db)
    c.url_fetch_status = "error"
    c.google_enriched_data = {"lookup_status": "success", "display_name": "X"}
    db.add(c)
    db.commit()
    p = approve_contribution_as_provider(
        db,
        c.id,
        ProviderApprovalFields(
            name="Verified Places Gym",
            description="Enough text here for provider desc field optional.",
            website="https://vp.example",
        ),
        "swim",
    )
    assert p.verified is True


def test_verified_false_when_both_signals_fail(db: Session) -> None:
    c = _provider_contribution(db)
    c.url_fetch_status = "timeout"
    c.google_enriched_data = {"lookup_status": "error", "error": "nope"}
    db.add(c)
    db.commit()
    p = approve_contribution_as_provider(
        db,
        c.id,
        ProviderApprovalFields(
            name="Unverified Gym",
            description="Enough text here for provider desc field optional.",
            website="https://uv.example",
        ),
        "swim",
    )
    assert p.verified is False


def test_entity_type_mismatch_raises(db: Session) -> None:
    c = _program_contribution(db)
    with pytest.raises(ValueError, match="entity type mismatch"):
        approve_contribution_as_provider(
            db,
            c.id,
            ProviderApprovalFields(
                name="Wrong",
                description="Enough text here for provider desc field optional.",
                website="https://w.example",
            ),
            "swim",
        )


def test_enrichment_suggests_verified_helper(db: Session) -> None:
    c = _provider_contribution(db)
    c.url_fetch_status = None
    c.google_enriched_data = None
    assert enrichment_suggests_verified(c) is False
    c.url_fetch_status = "success"
    assert enrichment_suggests_verified(c) is True
