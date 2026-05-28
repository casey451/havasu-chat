"""Phase 2B — four-tier sponsor_store helpers (slot + status filters)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import AdSlot, Sponsor, SponsorStatus
from app.home import sponsor_store


def _wipe(db: Session) -> None:
    db.query(Sponsor).delete()
    db.commit()


def _add(
    db: Session,
    *,
    slot: str = AdSlot.MARQUEE.value,
    status: str = SponsorStatus.APPROVED.value,
    active: bool = True,
    name: str = "Acme",
    weight: int = 0,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> Sponsor:
    sp = Sponsor(
        name=name,
        slot=slot,
        status=status,
        active=active,
        cta_url="https://example.com",
        weight=weight,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp


@pytest.fixture
def db() -> Session:
    with SessionLocal() as session:
        _wipe(session)
        yield session
        _wipe(session)


@pytest.mark.parametrize(
    ("helper", "slot", "limit"),
    [
        (sponsor_store.active_marquee, AdSlot.MARQUEE, 1),
        (sponsor_store.active_spotlights, AdSlot.SPOTLIGHT, 2),
        (sponsor_store.active_promoted, AdSlot.PROMOTED, 1),
        (sponsor_store.supporters, AdSlot.SUPPORTER, 4),
    ],
)
def test_live_helpers_return_only_approved_active_in_slot(
    db: Session,
    helper,
    slot: AdSlot,
    limit: int,
) -> None:
    """Each helper ignores wrong slot, non-approved status, and inactive rows."""
    wrong_slot = (
        AdSlot.SPOTLIGHT.value
        if slot == AdSlot.MARQUEE
        else AdSlot.MARQUEE.value
    )
    _add(db, slot=slot.value, name="winner")
    _add(db, slot=wrong_slot, name="wrong-slot")
    _add(db, slot=slot.value, status=SponsorStatus.DRAFT.value, name="draft")
    _add(db, slot=slot.value, active=False, name="inactive")

    if helper is sponsor_store.active_marquee or helper is sponsor_store.active_promoted:
        got = helper(db)
        assert got is not None
        assert got["name"] == "winner"
        assert got["headline"] == "winner"
    else:
        got = helper(db)
        assert len(got) == 1
        assert got[0]["name"] == "winner"


def test_active_spotlights_respects_limit_and_weight(db: Session) -> None:
    _add(db, slot=AdSlot.SPOTLIGHT.value, name="light", weight=1)
    _add(db, slot=AdSlot.SPOTLIGHT.value, name="heavy", weight=10)
    _add(db, slot=AdSlot.SPOTLIGHT.value, name="third", weight=5)
    rows = sponsor_store.active_spotlights(db, limit=2)
    assert [r["name"] for r in rows] == ["heavy", "third"]


def test_helpers_honor_booking_window(db: Session) -> None:
    now = now_lake_havasu()
    future = now + timedelta(days=1)
    past = now - timedelta(days=1)
    _add(
        db,
        slot=AdSlot.MARQUEE.value,
        name="future",
        starts_at=future.replace(tzinfo=LAKE_HAVASU_TZ),
    )
    _add(
        db,
        slot=AdSlot.MARQUEE.value,
        name="expired",
        ends_at=past.replace(tzinfo=LAKE_HAVASU_TZ),
    )
    assert sponsor_store.active_marquee(db) is None


def test_get_active_sponsor_is_marquee_shim(db: Session) -> None:
    _add(db, slot=AdSlot.MARQUEE.value, name="marquee-only")
    _add(db, slot=AdSlot.PROMOTED.value, name="not-marquee")
    got = sponsor_store.get_active_sponsor(db)
    assert got is not None and got["name"] == "marquee-only"
