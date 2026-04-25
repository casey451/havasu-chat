"""Tests for ``app.chat.context_builder`` (Tier 3 catalog context)."""

from __future__ import annotations

import re
from datetime import date, timedelta, time
from unittest.mock import patch

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.orm import Session

from app.chat.context_builder import (
    MAX_CONTEXT_WORDS,
    _unlinked_future_events,
    build_context_for_tier3,
)
from app.chat.intent_classifier import IntentResult
from app.db.database import SessionLocal
from app.db.models import Event, Program, Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def isolated_catalog(db: Session) -> Session:
    """Empty providers/programs/events for this test only; rolled back so the shared test DB stays clean."""
    nested = db.begin_nested()
    db.execute(delete(Program))
    db.execute(delete(Event))
    db.execute(delete(Provider))
    db.flush()
    yield db
    try:
        nested.rollback()
    except ResourceClosedError:
        pass


def _intent(*, entity: str | None = None, sub: str = "OPEN_ENDED") -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent=sub,
        confidence=0.8,
        entity=entity,
        raw_query="q",
        normalized_query="q",
    )


def test_entity_matched_provider_listed_first_with_details(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p_other = Provider(
        provider_name="Zebra Zoo",
        category="recreation",
        phone="111",
        verified=True,
        draft=False,
        is_active=True,
    )
    p_match = Provider(
        provider_name="Target Biz LLC",
        category="food",
        address="123 Main",
        phone="555-1212",
        website="https://target.example",
        hours="9-5",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add_all([p_other, p_match])
    db.flush()

    ctx = build_context_for_tier3("hours?", _intent(entity="Target Biz LLC"), db)
    names = re.findall(r"^Provider: (.+)$", ctx, re.MULTILINE)
    assert names[0] == "Target Biz LLC"
    assert "Provider: Zebra Zoo" in ctx
    assert "address: 123 Main" in ctx
    assert "phone: 555-1212" in ctx
    assert "website: https://target.example" in ctx
    assert "hours: 9-5" in ctx


def test_word_budget_respects_max_words(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Verbose Place",
        category="recreation",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    filler = "word " * 400
    prog = Program(
        title="T",
        description="Twenty chars minimum xx.",
        activity_category="sports",
        schedule_start_time="09:00",
        schedule_end_time="10:00",
        location_name="Here",
        provider_name=p.provider_name,
        provider_id=p.id,
        schedule_note=filler,
    )
    db.add(prog)
    db.flush()

    with patch("app.chat.context_builder.MAX_CONTEXT_WORDS", 80):
        ctx = build_context_for_tier3("q", _intent(), db)
    assert len(ctx.split()) <= 80


def test_default_context_word_count_at_most_budget(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Solo",
        category="recreation",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    ctx = build_context_for_tier3("anything", _intent(), db)
    assert len(ctx.split()) <= MAX_CONTEXT_WORDS


def test_draft_providers_excluded(isolated_catalog: Session) -> None:
    db = isolated_catalog
    db.add_all(
        [
            Provider(
                provider_name="Draft Only Inc",
                category="svc",
                draft=True,
                verified=False,
                is_active=True,
            ),
            Provider(
                provider_name="Real Co",
                category="svc",
                draft=False,
                verified=True,
                is_active=True,
            ),
        ]
    )
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    assert "Draft Only Inc" not in ctx
    assert "Real Co" in ctx


def test_inactive_programs_excluded(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Prog Shop",
        category="edu",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    db.add_all(
        [
            Program(
                title="Active Lesson",
                description="Twenty chars minimum xx.",
                activity_category="sports",
                schedule_start_time="09:00",
                schedule_end_time="10:00",
                location_name="Here",
                provider_name=p.provider_name,
                provider_id=p.id,
                is_active=True,
            ),
            Program(
                title="Hidden Lesson",
                description="Twenty chars minimum yy.",
                activity_category="sports",
                schedule_start_time="11:00",
                schedule_end_time="12:00",
                location_name="Here",
                provider_name=p.provider_name,
                provider_id=p.id,
                is_active=False,
            ),
        ]
    )
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    assert "Active Lesson" in ctx
    assert "Hidden Lesson" not in ctx


def test_past_events_excluded(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Event Host",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    today = date.today()
    db.add_all(
        [
            Event(
                title="Yesterday Gig",
                normalized_title="yesterday gig",
                date=today - timedelta(days=2),
                start_time=time(18, 0),
                location_name="Park",
                location_normalized="park",
                description="Twenty chars minimum ev.",
                provider_id=p.id,
                status="live",
            ),
            Event(
                title="Next Week Gig",
                normalized_title="next week gig",
                date=today + timedelta(days=9),
                start_time=time(18, 0),
                location_name="Park",
                location_normalized="park",
                description="Twenty chars minimum ev.",
                provider_id=p.id,
                status="live",
            ),
        ]
    )
    db.flush()
    ctx = build_context_for_tier3("events?", _intent(), db)
    assert "Yesterday Gig" not in ctx
    assert "Next Week Gig" in ctx


def test_long_hours_truncated(isolated_catalog: Session) -> None:
    db = isolated_catalog
    long_h = "x" * 250
    p = Provider(
        provider_name="Long Hours Biz",
        category="svc",
        hours=long_h,
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    ctx = build_context_for_tier3("hours?", _intent(entity="Long Hours Biz"), db)
    assert "hours: " in ctx
    start = ctx.index("hours: ") + len("hours: ")
    end = ctx.index("\n", start)
    hrs_val = ctx[start:end].strip()
    assert hrs_val.endswith("...")
    assert len(hrs_val) == 200


def test_at_most_ten_providers(isolated_catalog: Session) -> None:
    db = isolated_catalog
    for i in range(12):
        db.add(
            Provider(
                provider_name=f"Cap Provider {i:02d}",
                category="misc",
                verified=True,
                draft=False,
                is_active=True,
            )
        )
    db.flush()
    ctx = build_context_for_tier3("list all", _intent(), db)
    assert ctx.count("Provider:") == 10


def test_when_no_active_includes_verified_fallback_slice(isolated_catalog: Session) -> None:
    db = isolated_catalog
    for i in range(11):
        db.add(
            Provider(
                provider_name=f"Inactive Verified {i:02d}",
                category="misc",
                verified=True,
                draft=False,
                is_active=False,
            )
        )
    db.flush()
    ctx = build_context_for_tier3("open ended", _intent(entity=None), db)
    assert ctx.count("Provider:") == 10


def _unlinked_event_row(
    *,
    title: str,
    d: date,
    event_url: str = "",
) -> Event:
    return Event(
        title=title,
        normalized_title=title.lower(),
        date=d,
        start_time=time(10, 0),
        location_name="Lake",
        location_normalized="lake",
        description="Twenty chars minimum evnt.",
        provider_id=None,
        status="live",
        event_url=event_url,
    )


def test_unlinked_event_appears_under_general_calendar_header(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Linked Co",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    today = date.today()
    u = _unlinked_event_row(title="Standalone Fair", d=today + timedelta(days=7), event_url="https://e.example/x")
    db.add(u)
    db.flush()
    ctx = build_context_for_tier3("events", _intent(), db)
    assert "General calendar (upcoming, not attached to a listed business above):" in ctx
    assert "Standalone Fair" in ctx
    assert "https://e.example/x" in ctx
    assert f"on {u.date.isoformat()} at 10:00" in ctx


def test_unlinked_dedup_defensive_exclude_ids(isolated_catalog: Session) -> None:
    """Unlinked events whose id is in ``exclude_ids`` are dropped (defensive)."""
    db = isolated_catalog
    p = Provider(
        provider_name="Only for catalog",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    u = _unlinked_event_row(title="Would hide if excluded", d=date.today() + timedelta(days=1))
    db.add(u)
    db.flush()
    out = _unlinked_future_events(db, date.today(), {u.id})
    assert out == []


def test_unlinked_cap_respects_ten_earliest_by_date(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Host",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    day0 = date.today()
    for i in range(15):
        db.add(
            _unlinked_event_row(
                title=f"CapEvt{i:02d}",
                d=day0 + timedelta(days=i),
            )
        )
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    for i in range(10):
        assert f"CapEvt{i:02d}" in ctx
    for i in range(10, 15):
        assert f"CapEvt{i:02d}" not in ctx


def test_empty_unlinked_omits_general_calendar_section(isolated_catalog: Session) -> None:
    """Locked: zero unlinked future events → no General calendar header or block."""
    db = isolated_catalog
    p = Provider(
        provider_name="No unlinked",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    assert "General calendar" not in ctx
    assert "not attached to a listed business" not in ctx


def test_word_budget_reserved_tail_keeps_unlinked_visible(isolated_catalog: Session) -> None:
    p = Provider(
        provider_name="Verbose Host",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    isolated_catalog.add(p)
    isolated_catalog.flush()
    # Bloat the provider block via title (schedule_note is truncated to 120 chars in context).
    huge_title = "filler " * 2500
    isolated_catalog.add(
        Program(
            title=huge_title,
            description="Twenty chars minimum xx.",
            activity_category="sports",
            schedule_start_time="09:00",
            schedule_end_time="10:00",
            location_name="Here",
            provider_name=p.provider_name,
            provider_id=p.id,
            is_active=True,
        )
    )
    today = date.today()
    u = _unlinked_event_row(title="XYZZY_STANDALONE_RESERVE_42", d=today + timedelta(days=2))
    isolated_catalog.add(u)
    isolated_catalog.flush()
    ctx = build_context_for_tier3("q", _intent(), isolated_catalog)
    assert "XYZZY_STANDALONE_RESERVE_42" in ctx
    assert "General calendar" in ctx
    # Provider blob was truncated, but the block after reserved tail is intact
    pos_gcal = ctx.index("General calendar")
    assert "XYZZY_STANDALONE_RESERVE_42" in ctx[pos_gcal:]


def test_unlinked_excluded_past_365_day_upper_bound(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Host",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    t0 = date.today()
    far = _unlinked_event_row(title="Too Far Out 400d", d=t0 + timedelta(days=400))
    near = _unlinked_event_row(title="Within 300d OK", d=t0 + timedelta(days=300))
    db.add_all([far, near])
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    assert "Within 300d OK" in ctx
    assert "Too Far Out 400d" not in ctx


def test_unlinked_ordering_date_ascending(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Host",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    t0 = date.today()
    a = _unlinked_event_row(title="Second date", d=t0 + timedelta(days=20))
    b = _unlinked_event_row(title="First date", d=t0 + timedelta(days=2))
    c = _unlinked_event_row(title="Third date", d=t0 + timedelta(days=200))
    db.add_all([a, b, c])
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    i_first = ctx.index("First date")
    i_second = ctx.index("Second date")
    i_third = ctx.index("Third date")
    assert i_first < i_second < i_third
