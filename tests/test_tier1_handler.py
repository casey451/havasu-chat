"""Tests for ``app.chat.tier1_handler`` (Phase 3.1 Tier 1 wiring)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.chat.tier1_handler import try_tier1
from app.db.models import Event, Program, Provider


def _intent(
    *,
    sub: str,
    entity: str | None,
    nq: str = "",
) -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent=sub,
        confidence=0.9,
        entity=entity,
        raw_query="fixture",
        normalized_query=nq or "fixture",
    )


def _provider(**kwargs: object) -> Provider:
    defaults: dict[str, object] = {
        "provider_name": "Tier1 Test Gym",
        "category": "sports",
        "verified": False,
        "draft": False,
        "is_active": True,
        "source": "seed",
    }
    defaults.update(kwargs)
    return Provider(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_entity_none_returns_none(db: Session) -> None:
    ir = _intent(sub="TIME_LOOKUP", entity=None)
    assert try_tier1("anything", ir, db) is None


def test_sub_intent_open_ended_returns_none(db: Session) -> None:
    p = _provider(provider_name="P1", phone="555-000-0001")
    db.add(p)
    db.commit()
    ir = _intent(sub="OPEN_ENDED", entity=p.provider_name)
    assert try_tier1("recommend something", ir, db) is None


def test_provider_missing_returns_none(db: Session) -> None:
    ir = _intent(sub="PHONE_LOOKUP", entity="No Such Provider Name XYZ")
    assert try_tier1("phone", ir, db) is None


def test_phone_lookup(db: Session) -> None:
    p = _provider(provider_name="PhoneCo", phone="928-555-0100")
    db.add(p)
    db.commit()
    ir = _intent(sub="PHONE_LOOKUP", entity=p.provider_name, nq="phone number for phoneco")
    out = try_tier1("What is the phone number for PhoneCo?", ir, db)
    assert out is not None
    assert "928-555-0100" in out
    assert not out.rstrip().endswith("?")


def test_location_and_website(db: Session) -> None:
    p = _provider(
        provider_name="LocCo",
        address="100 Main St, Lake Havasu City, AZ",
        website="https://example.com/loc",
    )
    db.add(p)
    db.commit()
    loc = try_tier1("where", _intent(sub="LOCATION_LOOKUP", entity=p.provider_name), db)
    assert loc is not None and "100 Main St" in loc
    web = try_tier1("website", _intent(sub="WEBSITE_LOOKUP", entity=p.provider_name), db)
    assert web is not None and "example.com" in web


def test_hours_lookup(db: Session) -> None:
    p = _provider(provider_name="HoursCo", hours="Mon–Sun 9:00 AM – 8:00 PM")
    db.add(p)
    db.commit()
    out = try_tier1("hours", _intent(sub="HOURS_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert "9:00" in out or "Mon" in out


def test_time_lookup_uses_hours_when_set(db: Session) -> None:
    p = _provider(provider_name="TimeCo", hours="Daily 10:00 AM – 6:00 PM")
    db.add(p)
    db.commit()
    out = try_tier1("what time", _intent(sub="TIME_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert "10:00" in out or "Daily" in out


def test_time_lookup_falls_back_to_program_schedule(db: Session) -> None:
    p = _provider(provider_name="SchedCo", hours="")
    db.add(p)
    db.flush()
    prog = Program(
        title="Tiny Tumblers",
        description="Twenty characters minimum here.",
        activity_category="sports",
        schedule_days=["Saturday"],
        schedule_start_time="09:30",
        schedule_end_time="10:30",
        location_name="Lake Havasu City",
        provider_name=p.provider_name,
        provider_id=p.id,
        source="admin",
    )
    db.add(prog)
    db.commit()
    ir = _intent(
        sub="TIME_LOOKUP",
        entity=p.provider_name,
        nq="what time does tiny tumblers start",
    )
    out = try_tier1("What time does Tiny Tumblers start at SchedCo?", ir, db)
    assert out is not None
    assert "09:30" in out


def test_phone_null_returns_none(db: Session) -> None:
    p = _provider(provider_name="NoPhoneCo", phone=None)
    db.add(p)
    db.commit()
    assert try_tier1("phone", _intent(sub="PHONE_LOOKUP", entity=p.provider_name), db) is None


def test_cost_program_cost(db: Session) -> None:
    p = _provider(provider_name="MoneyCo")
    db.add(p)
    db.flush()
    prog = Program(
        title="Drop-in Class",
        description="Twenty characters minimum here.",
        activity_category="sports",
        schedule_days=["Monday"],
        schedule_start_time="10:00",
        schedule_end_time="11:00",
        location_name="Lake Havasu City",
        provider_name=p.provider_name,
        provider_id=p.id,
        cost="$15 per session",
        show_pricing_cta=False,
        source="admin",
    )
    db.add(prog)
    db.commit()
    out = try_tier1("how much", _intent(sub="COST_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert "$15" in out


def test_cost_contact_cta(db: Session) -> None:
    p = _provider(provider_name="CtaCo", phone="928-555-0202")
    db.add(p)
    db.flush()
    prog = Program(
        title="Private Lesson",
        description="Twenty characters minimum here.",
        activity_category="sports",
        schedule_days=["Tuesday"],
        schedule_start_time="14:00",
        schedule_end_time="15:00",
        location_name="Lake Havasu City",
        provider_name=p.provider_name,
        provider_id=p.id,
        cost=None,
        show_pricing_cta=True,
        contact_phone="928-555-0303",
        source="admin",
    )
    db.add(prog)
    db.commit()
    out = try_tier1("how much", _intent(sub="COST_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert "call" in out.lower() or "pricing" in out.lower()


def test_age_lookup(db: Session) -> None:
    p = _provider(provider_name="AgeCo")
    db.add(p)
    db.flush()
    prog = Program(
        title="Kids Camp",
        description="Twenty characters minimum here.",
        activity_category="sports",
        schedule_days=["Monday"],
        schedule_start_time="09:00",
        schedule_end_time="12:00",
        location_name="Lake Havasu City",
        provider_name=p.provider_name,
        provider_id=p.id,
        age_min=5,
        age_max=10,
        source="admin",
    )
    db.add(prog)
    db.commit()
    out = try_tier1("ages", _intent(sub="AGE_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert "5" in out and "10" in out


def test_verified_suffix(db: Session) -> None:
    p = _provider(provider_name="VerCo", phone="928-555-0404", verified=True)
    db.add(p)
    db.commit()
    out = try_tier1("phone", _intent(sub="PHONE_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert "(confirmed)" in out


def test_date_next_event(db: Session) -> None:
    p = _provider(provider_name="EvtCo")
    db.add(p)
    db.flush()
    ev = Event(
        title="Summer Kickoff",
        normalized_title="summer kickoff",
        date=date(2099, 7, 4),
        start_time=time(18, 0),
        end_time=time(21, 0),
        location_name="London Bridge Beach",
        location_normalized="london bridge beach",
        description="Twenty characters minimum description.",
        event_url="https://example.com/e",
        provider_id=p.id,
        status="live",
        source="admin",
    )
    db.add(ev)
    db.commit()
    for sub in ("DATE_LOOKUP", "NEXT_OCCURRENCE"):
        out = try_tier1("when", _intent(sub=sub, entity=p.provider_name), db)
        assert out is not None
        assert "2099-07-04" in out or "Summer Kickoff" in out


def test_open_now_in_window(db: Session) -> None:
    p = _provider(provider_name="OpenCo", hours="10:00 AM – 9:00 PM")
    db.add(p)
    db.commit()
    fixed = datetime(2026, 4, 19, 14, 0, 0, tzinfo=UTC)
    with patch("app.chat.tier1_handler._utcnow", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "open" in out.lower()


def test_open_now_outside_window(db: Session) -> None:
    p = _provider(provider_name="ClosedCo", hours="10:00 AM – 9:00 PM")
    db.add(p)
    db.commit()
    fixed = datetime(2026, 4, 19, 22, 30, 0, tzinfo=UTC)
    with patch("app.chat.tier1_handler._utcnow", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "closed" in out.lower()


def test_open_now_unparseable(db: Session) -> None:
    p = _provider(provider_name="FuzzyHoursCo", hours="call for seasonal hours")
    db.add(p)
    db.commit()
    with patch("app.chat.tier1_handler._utcnow", return_value=datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)):
        assert try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db) is None


def test_simple_lookup_length(db: Session) -> None:
    p = _provider(provider_name="ShortCo", phone="928-555-0505")
    db.add(p)
    db.commit()
    out = try_tier1("phone", _intent(sub="PHONE_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert len(out) < 200
