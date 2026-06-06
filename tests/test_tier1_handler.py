"""Tests for ``app.chat.tier1_handler`` (Phase 3.1 Tier 1 wiring)."""

from __future__ import annotations

import unittest
from datetime import date, datetime, time
from datetime import datetime as _dt
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.chat import tier1_handler as _t1
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


def test_hours_lookup_day_focus_with_pipe_hours(db: Session) -> None:
    p = _provider(
        provider_name="DayPipeCo",
        hours="Sun 11am–7pm | Fri 11am–8pm | Sat 9am–9pm",
    )
    db.add(p)
    db.commit()
    nq = "is daypipeco open late on friday"
    ir = _intent(sub="HOURS_LOOKUP", entity=p.provider_name, nq=nq)
    out = try_tier1("Is DayPipeCo open late on friday?", ir, db)
    assert out is not None
    low = out.lower()
    assert "friday" in low
    assert "11am" in low
    assert "|" not in out


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
        schedule_start_time=time(9, 30),
        schedule_end_time=time(10, 30),
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
        schedule_start_time=time(10, 0),
        schedule_end_time=time(11, 0),
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
        schedule_start_time=time(14, 0),
        schedule_end_time=time(15, 0),
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
        schedule_start_time=time(9, 0),
        schedule_end_time=time(12, 0),
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
    # Slice 41 / Backlog #27: tier1_handler now patches now_lake_havasu;
    # tzinfo must be Lake Havasu local for the wall-clock comparison.
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed = datetime(2026, 4, 19, 14, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "open" in out.lower()


def test_open_now_outside_window(db: Session) -> None:
    p = _provider(provider_name="ClosedCo", hours="10:00 AM – 9:00 PM")
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    # 22:30 local time (10:30pm) is outside a 10am-9pm window.
    fixed = datetime(2026, 4, 19, 22, 30, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "closed" in out.lower()


def test_open_now_unparseable(db: Session) -> None:
    p = _provider(provider_name="FuzzyHoursCo", hours="call for seasonal hours")
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    with patch(
        "app.chat.tier1_handler.now_lake_havasu",
        return_value=datetime(2026, 4, 19, 12, 0, 0, tzinfo=havasu_tz),
    ):
        assert try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db) is None


def test_simple_lookup_length(db: Session) -> None:
    p = _provider(provider_name="ShortCo", phone="928-555-0505")
    db.add(p)
    db.commit()
    out = try_tier1("phone", _intent(sub="PHONE_LOOKUP", entity=p.provider_name), db)
    assert out is not None
    assert len(out) < 200


# Slice 41 / Backlog #27 — OPEN_NOW + _next_event use Lake Havasu local time, not UTC.


def test_open_now_uses_lake_havasu_local_time() -> None:
    """Backlog #27 fix: OPEN_NOW compares against Lake Havasu local hours,
    not UTC. Frozen time at 10am MST should be inside a 9am-5pm window
    and outside an 11am-5pm window.
    """
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed_local_10am = _dt(2026, 5, 4, 10, 0, tzinfo=havasu_tz)

    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed_local_10am):
        is_open = _t1._open_now_from_hours("9am-5pm", fixed_local_10am.replace(tzinfo=None))
        assert is_open is True, "10am should be open during 9am-5pm window"

        is_closed = _t1._open_now_from_hours("11am-5pm", fixed_local_10am.replace(tzinfo=None))
        assert is_closed is False, "10am should be closed before 11am-5pm window"


def test_open_now_from_hours_respects_weekday_range() -> None:
    """P1-7: 'Mon-Fri 9am-5pm' is closed on Sunday even at 10am, open Wednesday."""
    sunday = _dt(2024, 1, 7, 10, 0)
    assert sunday.weekday() == 6
    wednesday = _dt(2024, 1, 3, 10, 0)
    assert wednesday.weekday() == 2
    assert _t1._open_now_from_hours("Mon-Fri 9am-5pm", sunday) is False
    assert _t1._open_now_from_hours("Mon-Fri 9am-5pm", wednesday) is True


def test_open_now_from_hours_handles_after_midnight() -> None:
    """P1-7: a window crossing midnight ('5pm-2am') is open at 1am, closed at 3pm."""
    one_am = _dt(2024, 1, 3, 1, 0)
    three_pm = _dt(2024, 1, 3, 15, 0)
    eleven_pm = _dt(2024, 1, 3, 23, 0)
    assert _t1._open_now_from_hours("5pm-2am", one_am) is True
    assert _t1._open_now_from_hours("5pm-2am", three_pm) is False
    assert _t1._open_now_from_hours("5pm-2am", eleven_pm) is True


def test_next_event_uses_lake_havasu_today() -> None:
    """Backlog #27 fix: _next_event uses today's date in Lake Havasu local
    time, not UTC. Important for ~7am MST queries when UTC has already
    rolled to the next day. At 11:30pm MST on 2026-05-04, UTC is already
    at 06:30 on 2026-05-05; the helper must produce 2026-05-04.
    """
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed_local = _dt(2026, 5, 4, 23, 30, tzinfo=havasu_tz)

    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed_local):
        observed_date = _t1.now_lake_havasu().date()
        assert observed_date.year == 2026
        assert observed_date.month == 5
        assert observed_date.day == 4, (
            f"Expected today=2026-05-04 (Lake Havasu local), got {observed_date}"
        )


# ---------------------------------------------------------------------------
# Slice B: Google business retrieval — google_hours JSON fallback
# ---------------------------------------------------------------------------


def _google_hours_periods(*ranges: tuple[int, int, int, int, int, int]) -> dict:
    """Build a Google Places ``regular_opening_hours`` blob for tests.

    Each range is ``(open_day, open_hour, open_min, close_day, close_hour, close_min)``
    where day uses Google's convention (0=Sun … 6=Sat).
    """
    periods = []
    for od, oh, om, cd, ch, cm in ranges:
        periods.append(
            {
                "open": {"day": od, "hour": oh, "minute": om},
                "close": {"day": cd, "hour": ch, "minute": cm},
            }
        )
    return {"periods": periods, "weekdayDescriptions": []}


def test_hours_text_from_google_strips_weekday_colon() -> None:
    """``Monday: 9:00 AM – 5:00 PM`` → ``Monday 9:00 AM – 5:00 PM`` so the existing
    weekday-aware template parser (which expects a bare weekday as the first token) works."""
    out = _t1._hours_text_from_google(
        {
            "weekdayDescriptions": [
                "Monday: 9:00 AM – 5:00 PM",
                "Tuesday: 9:00 AM – 5:00 PM",
                "Sunday: Closed",
            ]
        }
    )
    assert out is not None
    parts = out.split(" | ")
    assert parts[0] == "Monday 9:00 AM – 5:00 PM"
    assert parts[1] == "Tuesday 9:00 AM – 5:00 PM"
    assert parts[2] == "Sunday Closed"


def test_hours_text_from_google_returns_none_when_missing() -> None:
    assert _t1._hours_text_from_google(None) is None
    assert _t1._hours_text_from_google({}) is None
    assert _t1._hours_text_from_google({"weekdayDescriptions": []}) is None
    assert _t1._hours_text_from_google({"weekdayDescriptions": ["", "  "]}) is None


def test_provider_hours_text_prefers_legacy_field() -> None:
    """When both fields are populated, the legacy free-text ``provider.hours``
    wins (it's operator-curated; google_hours is auto-pulled and may be stale)."""
    p = _provider(
        provider_name="Both",
        hours="9am-5pm Mon-Fri",
        google_hours={"weekdayDescriptions": ["Monday: 8:00 AM – 6:00 PM"]},
    )
    assert _t1._provider_hours_text(p) == "9am-5pm Mon-Fri"


def test_provider_hours_text_falls_back_to_google() -> None:
    p = _provider(
        provider_name="GoogleOnly",
        hours=None,
        google_hours={"weekdayDescriptions": ["Monday: 9:00 AM – 5:00 PM"]},
    )
    out = _t1._provider_hours_text(p)
    assert out == "Monday 9:00 AM – 5:00 PM"


def test_hours_lookup_uses_google_hours_when_legacy_empty(db: Session) -> None:
    p = _provider(
        provider_name="GoogleHoursCo",
        source="google_places",
        google_place_id="test_google_hours_co",
        hours=None,
        google_hours={
            "weekdayDescriptions": [
                "Monday: 9:00 AM – 5:00 PM",
                "Tuesday: 9:00 AM – 5:00 PM",
            ],
            "periods": [],
        },
    )
    db.add(p)
    db.commit()
    out = try_tier1(
        "hours for googlehoursco", _intent(sub="HOURS_LOOKUP", entity=p.provider_name), db
    )
    assert out is not None
    assert "Monday" in out and "9:00 AM" in out


def test_open_now_via_google_periods_in_window(db: Session) -> None:
    """Google providers with ``google_hours.periods`` should compute open-now correctly
    via the structured-hours path even when ``provider.hours`` is empty."""
    p = _provider(
        provider_name="GoogleOpenCo",
        source="google_places",
        google_place_id="test_google_open_co",
        hours=None,
        # Mon-Fri 9:00-17:00 (Google: 1=Mon, ..., 5=Fri)
        google_hours=_google_hours_periods(
            (1, 9, 0, 1, 17, 0),
            (2, 9, 0, 2, 17, 0),
            (3, 9, 0, 3, 17, 0),
            (4, 9, 0, 4, 17, 0),
            (5, 9, 0, 5, 17, 0),
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    # Tuesday 2026-05-05 14:00 local — inside the 9-5 window.
    fixed = datetime(2026, 5, 5, 14, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "open" in out.lower()


def test_open_now_via_google_periods_outside_window(db: Session) -> None:
    p = _provider(
        provider_name="GoogleClosedCo",
        source="google_places",
        google_place_id="test_google_closed_co",
        hours=None,
        google_hours=_google_hours_periods(
            (1, 9, 0, 1, 17, 0),
            (2, 9, 0, 2, 17, 0),
            (3, 9, 0, 3, 17, 0),
            (4, 9, 0, 4, 17, 0),
            (5, 9, 0, 5, 17, 0),
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    # Tuesday 2026-05-05 22:00 local — well outside the 9-5 window.
    fixed = datetime(2026, 5, 5, 22, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "closed" in out.lower()


def test_open_now_via_google_periods_split_day_windows(db: Session) -> None:
    """A restaurant open lunch 11:00-14:00 then dinner 17:00-22:00 should report
    open at 12:30, closed at 15:00, open at 19:00. The legacy regex parser only
    sees one window — the structured path must catch both."""
    p = _provider(
        provider_name="LunchAndDinnerCo",
        source="google_places",
        google_place_id="test_lunch_dinner_co",
        hours=None,
        # Tuesday lunch + dinner segments
        google_hours=_google_hours_periods(
            (2, 11, 0, 2, 14, 0),
            (2, 17, 0, 2, 22, 0),
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    cases = [
        (datetime(2026, 5, 5, 12, 30, 0, tzinfo=havasu_tz), "open"),
        (datetime(2026, 5, 5, 15, 0, 0, tzinfo=havasu_tz), "closed"),
        (datetime(2026, 5, 5, 19, 0, 0, tzinfo=havasu_tz), "open"),
    ]
    for fixed, expected in cases:
        with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
            out = try_tier1(
                "open now",
                _intent(sub="OPEN_NOW", entity=p.provider_name),
                db,
            )
        assert out is not None, f"no answer at {fixed}"
        assert expected in out.lower(), f"expected {expected} at {fixed}, got {out!r}"


def test_open_now_returns_none_when_no_hours_anywhere(db: Session) -> None:
    p = _provider(
        provider_name="NoHoursAtAllCo",
        source="google_places",
        google_place_id="test_no_hours_co",
        hours=None,
        google_hours=None,
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed = datetime(2026, 5, 5, 14, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is None


def test_time_lookup_falls_back_to_google_hours_for_provider_without_programs(db: Session) -> None:
    """Google providers have no Programs. TIME_LOOKUP should still answer via the
    google_hours fallback rather than returning None."""
    p = _provider(
        provider_name="GoogleTimeCo",
        source="google_places",
        google_place_id="test_google_time_co",
        hours=None,
        google_hours={
            "weekdayDescriptions": [
                "Monday: 8:00 AM – 6:00 PM",
                "Tuesday: 8:00 AM – 6:00 PM",
            ]
        },
    )
    db.add(p)
    db.commit()
    out = try_tier1(
        "what time does googletimeco open",
        _intent(sub="TIME_LOOKUP", entity=p.provider_name),
        db,
    )
    assert out is not None
    assert "8:00 AM" in out


# ---------------------------------------------------------------------------
# Slice C: RATING_LOOKUP and REVIEW_COUNT_LOOKUP
# ---------------------------------------------------------------------------


def test_rating_lookup_with_review_count(db: Session) -> None:
    p = _provider(
        provider_name="MudsharkBrewing",
        source="google_places",
        google_place_id="test_mudshark",
        google_rating=4.6,
        google_review_count=423,
    )
    db.add(p)
    db.commit()
    out = try_tier1(
        "what is the rating for mudshark",
        _intent(sub="RATING_LOOKUP", entity=p.provider_name),
        db,
    )
    assert out is not None
    assert "4.6" in out
    assert "423" in out


def test_rating_lookup_formats_one_decimal(db: Session) -> None:
    """Rating renders to one decimal so 4.5 doesn't surface as 4.5 vs 4.50 vs 4.499999."""
    p = _provider(
        provider_name="DecimalCo",
        source="google_places",
        google_place_id="test_decimal",
        google_rating=4.5,
        google_review_count=12,
    )
    db.add(p)
    db.commit()
    out = try_tier1(
        "rating for decimalco",
        _intent(sub="RATING_LOOKUP", entity=p.provider_name),
        db,
    )
    assert out is not None
    assert "4.5" in out
    assert "4.50" not in out
    assert "4.5-star" in out or "4.5 stars" in out


def test_rating_lookup_without_reviews_uses_no_reviews_variant(db: Session) -> None:
    """Some Google places have a rating but ~0 reviews (low traffic). Switch to the
    *_NO_REVIEWS variant so the response doesn't read "(0 reviews)"."""
    p = _provider(
        provider_name="LowTrafficCo",
        source="google_places",
        google_place_id="test_lowtraffic",
        google_rating=5.0,
        google_review_count=0,
    )
    db.add(p)
    db.commit()
    out = try_tier1(
        "rating for lowtrafficco",
        _intent(sub="RATING_LOOKUP", entity=p.provider_name),
        db,
    )
    assert out is not None
    assert "5.0" in out
    assert "0 reviews" not in out
    assert "( reviews)" not in out


def test_rating_lookup_returns_none_when_no_rating(db: Session) -> None:
    """~16% of pulled rows lack ratings; handler must fall through to Tier 3 cleanly."""
    p = _provider(
        provider_name="UnratedCo",
        source="google_places",
        google_place_id="test_unrated",
        google_rating=None,
        google_review_count=None,
    )
    db.add(p)
    db.commit()
    assert (
        try_tier1(
            "rating for unratedco",
            _intent(sub="RATING_LOOKUP", entity=p.provider_name),
            db,
        )
        is None
    )


def test_review_count_lookup(db: Session) -> None:
    p = _provider(
        provider_name="PopularCo",
        source="google_places",
        google_place_id="test_popular",
        google_rating=4.2,
        google_review_count=1547,
    )
    db.add(p)
    db.commit()
    out = try_tier1(
        "how many reviews does popularco have",
        _intent(sub="REVIEW_COUNT_LOOKUP", entity=p.provider_name),
        db,
    )
    assert out is not None
    assert "1547" in out


def test_review_count_lookup_returns_none_when_zero(db: Session) -> None:
    p = _provider(
        provider_name="NoReviewsCo",
        source="google_places",
        google_place_id="test_noreviews",
        google_rating=None,
        google_review_count=0,
    )
    db.add(p)
    db.commit()
    assert (
        try_tier1(
            "how many reviews does noreviewsco have",
            _intent(sub="REVIEW_COUNT_LOOKUP", entity=p.provider_name),
            db,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Slice F1: OPEN_NOW with hours context
# ---------------------------------------------------------------------------


def test_open_now_open_includes_close_time_structured(db: Session) -> None:
    """Open + structured hours: response must surface today's close time, not the sterile
    'in window for today' phrasing."""
    p = _provider(
        provider_name="OpenF1Co",
        source="google_places",
        google_place_id="test_openf1",
        hours=None,
        google_hours=_google_hours_periods(
            (1, 9, 0, 1, 17, 0),
            (2, 9, 0, 2, 17, 0),
            (3, 9, 0, 3, 17, 0),
            (4, 9, 0, 4, 17, 0),
            (5, 9, 0, 5, 17, 0),
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed = datetime(2026, 5, 5, 14, 0, 0, tzinfo=havasu_tz)  # Tuesday 2 PM
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "Open right now" in out
    assert "5 PM" in out
    assert "in window for today" not in out  # old sterile wording must be gone


def test_open_now_closed_includes_next_open_today(db: Session) -> None:
    """Closed earlier in the day with same-day open later: response says when it opens today."""
    p = _provider(
        provider_name="ClosedEarlyF1Co",
        source="google_places",
        google_place_id="test_closedearlyf1",
        hours=None,
        google_hours=_google_hours_periods(
            (2, 9, 0, 2, 17, 0),  # Tuesday 9 AM – 5 PM
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed = datetime(2026, 5, 5, 7, 0, 0, tzinfo=havasu_tz)  # Tuesday 7 AM
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "Closed right now" in out
    assert "opens at 9 AM" in out
    assert "today" in out


def test_open_now_closed_today_opens_tomorrow(db: Session) -> None:
    """After today's close, response surfaces tomorrow's window."""
    p = _provider(
        provider_name="ClosedTodayF1Co",
        source="google_places",
        google_place_id="test_closedtodayf1",
        hours=None,
        google_hours=_google_hours_periods(
            (2, 9, 0, 2, 17, 0),  # Tuesday 9 AM – 5 PM
            (3, 9, 0, 3, 17, 0),  # Wednesday 9 AM – 5 PM
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    # Tuesday 22:00 (10 PM) — past Tuesday's close, before Wednesday's open.
    fixed = datetime(2026, 5, 5, 22, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "Closed today" in out
    assert "tomorrow" in out
    assert "9 AM" in out
    assert "5 PM" in out


def test_open_now_closed_today_opens_named_weekday(db: Session) -> None:
    """When closed today and tomorrow with no open segments, response names the next open weekday."""
    p = _provider(
        provider_name="WeekdayOnlyF1Co",
        source="google_places",
        google_place_id="test_weekdayonlyf1",
        hours=None,
        google_hours=_google_hours_periods(
            (1, 9, 0, 1, 17, 0),  # Monday only
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    # Saturday 12:00 — closed today, closed tomorrow (Sunday), opens Monday.
    fixed = datetime(2026, 5, 9, 12, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "Closed today" in out
    assert "Monday" in out
    assert "9 AM" in out


def test_open_now_split_day_during_break_says_next_segment(db: Session) -> None:
    """Restaurant with lunch + dinner: between segments → 'opens at 5 PM today' (dinner segment)."""
    p = _provider(
        provider_name="LunchDinnerF1Co",
        source="google_places",
        google_place_id="test_lunchdinnerf1",
        hours=None,
        google_hours=_google_hours_periods(
            (2, 11, 0, 2, 14, 0),  # Tuesday lunch
            (2, 17, 0, 2, 22, 0),  # Tuesday dinner
        ),
    )
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed = datetime(2026, 5, 5, 15, 30, 0, tzinfo=havasu_tz)  # 3:30 PM — between segments
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "Closed right now" in out
    assert "opens at 5 PM" in out


def test_open_now_legacy_freetext_open_includes_close_time(db: Session) -> None:
    """Free-text hours path (non-Google providers) also surfaces close time when open."""
    p = _provider(provider_name="FreeTextOpenCo", hours="10:00 AM – 9:00 PM")
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    fixed = datetime(2026, 4, 19, 14, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "Open right now" in out
    assert "9 PM" in out


def test_open_now_legacy_freetext_closed_includes_open_time(db: Session) -> None:
    p = _provider(provider_name="FreeTextClosedCo", hours="10:00 AM – 9:00 PM")
    db.add(p)
    db.commit()
    havasu_tz = ZoneInfo("America/Phoenix")
    # 7 AM — before today's open
    fixed = datetime(2026, 4, 19, 7, 0, 0, tzinfo=havasu_tz)
    with patch("app.chat.tier1_handler.now_lake_havasu", return_value=fixed):
        out = try_tier1("open now", _intent(sub="OPEN_NOW", entity=p.provider_name), db)
    assert out is not None
    assert "Closed right now" in out
    assert "opens at 10 AM" in out


class AboutCardTests(unittest.TestCase):
    """Zero-token entity-about answers ('tell me about X') from catalog columns."""

    def _provider(self, **kw):
        from app.db.models import Provider

        defaults = dict(
            provider_name="Mudshark Brewery and Public House",
            category="restaurant",
            google_primary_category="Brewery",
            google_rating=4.6,
            google_review_count=454,
            address="210 Swanson Ave, Lake Havasu City, AZ",
            phone="(928) 453-9302",
        )
        defaults.update(kw)
        return Provider(**defaults)

    def test_full_card(self) -> None:
        from app.chat.tier1_handler import _render_about_card

        out = _render_about_card(self._provider())
        assert out is not None
        self.assertIn("Mudshark Brewery and Public House — Brewery.", out)
        self.assertIn("4.6 (454 reviews) on Google.", out)
        self.assertIn("210 Swanson Ave", out)
        self.assertIn("(928) 453-9302.", out)

    def test_minimal_card_skips_missing_fields(self) -> None:
        from app.chat.tier1_handler import _render_about_card

        out = _render_about_card(
            self._provider(
                google_rating=None, google_review_count=None, address=None, phone=None
            )
        )
        self.assertEqual(out, "Mudshark Brewery and Public House — Brewery.")

    def test_no_category_falls_through(self) -> None:
        from app.chat.tier1_handler import _render_about_card

        self.assertIsNone(
            _render_about_card(self._provider(google_primary_category=None, category=None))
        )
