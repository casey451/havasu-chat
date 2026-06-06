"""venue_schedule intent (2026-06-06 gap report follow-up).

A matched venue + schedule words answers from that venue's programs/events at
0 tokens. Factual lookups and about-shapes keep declining to the entity path.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.chat.intents.queries import _venue_core_tokens
from app.chat.intents.runtime import _wants_venue_schedule, try_intent_layer
from app.db.database import SessionLocal
from app.db.models import Event, Program, QueryLog


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    with SessionLocal() as session:
        yield session
        # The suite shares one SQLite file per worker — clean up seeded rows so
        # ordering doesn't leak venues across tests (XDIST_TEST_ISOLATION docs).
        session.query(Program).filter(Program.source == "test").delete()
        session.query(Event).filter(Event.source == "test").delete()
        session.commit()


def _seed_program(session, *, title, provider_name, location_name):
    session.add(
        Program(
            title=title,
            description="test",
            activity_category="aquatics",
            schedule_days=["monday", "wednesday"],
            schedule_start_time=time(9, 0),
            schedule_end_time=time(10, 0),
            location_name=location_name,
            provider_name=provider_name,
            source="test",
            is_active=True,
        )
    )
    session.commit()


def _seed_event(session, *, title, location_name, days_ahead=1):
    d = date.today() + timedelta(days=days_ahead)
    session.add(
        Event(
            title=title,
            normalized_title=title.lower(),
            date=d,
            start_time=time(12, 0),
            location_name=location_name,
            location_normalized=location_name.lower(),
            description="test",
            status="live",
            source="test",
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_venue_core_tokens_drop_town_words():
    assert _venue_core_tokens("Lake Havasu City Aquatic Center") == ["aquatic", "center"]
    assert _venue_core_tokens("Mudshark Brewery and Public House") == [
        "mudshark",
        "brewery",
        "public",
        "house",
    ]
    assert _venue_core_tokens("Lake Havasu City") == []


@pytest.mark.parametrize(
    "query, expected",
    [
        ("what water exercise classes does the aquatic center offer and when", True),
        ("what is going on at the aquatic center this week", True),
        ("aquatic center schedule", True),
        ("sign up for swim lessons at the aquatic center", True),
        ("what time does the aquatic center close", False),
        ("phone for the aquatic center", False),
        ("where is the aquatic center", False),
    ],
)
def test_wants_venue_schedule(query, expected):
    assert _wants_venue_schedule(query) is expected


# ---------------------------------------------------------------------------
# End-to-end through try_intent_layer
# ---------------------------------------------------------------------------


def test_venue_schedule_claims_with_programs(db):
    _seed_program(
        db,
        title="Water Aerobics",
        provider_name="Lake Havasu City Aquatic Center",
        location_name="Lake Havasu City Aquatic Center",
    )
    ans = try_intent_layer(
        "what water exercise classes does the aquatic center offer and when",
        db,
        entity="Lake Havasu City Aquatic Center",
        sub_intent="OPEN_ENDED",
    )
    assert ans is not None
    assert ans.intent_key == "venue_schedule"
    assert ans.result_count == 1
    assert "Water Aerobics" in ans.text


def test_venue_schedule_matches_feed_spelling_variant(db):
    # The events feed drops "City": "Lake Havasu Aquatic Center" must still hit.
    _seed_event(db, title="Open Swim", location_name="Lake Havasu Aquatic Center")
    ans = try_intent_layer(
        "what is happening at the aquatic center this week",
        db,
        entity="Lake Havasu City Aquatic Center",
        sub_intent="OPEN_ENDED",
    )
    assert ans is not None
    assert ans.intent_key == "venue_schedule"
    assert "Open Swim" in ans.text


def test_venue_schedule_zero_rows_falls_through_and_logs(db):
    ans = try_intent_layer(
        "what classes does the desert bloom learning center offer",
        db,
        entity="Desert Bloom Learning Center",
        sub_intent="OPEN_ENDED",
    )
    assert ans is None  # honest fall-through on empty
    # query_log rows from sibling tests share the file; assert OUR zero-row
    # coverage signal exists rather than inspecting whichever row sorts first.
    row = db.scalars(
        select(QueryLog).where(
            QueryLog.normalized_intent == "venue_schedule",
            QueryLog.result_count == 0,
        )
    ).first()
    assert row is not None  # coverage signal logged


def test_factual_lookup_still_declines(db):
    _seed_event(db, title="Open Swim", location_name="Lake Havasu Aquatic Center")
    ans = try_intent_layer(
        "what time does the aquatic center close",
        db,
        entity="Lake Havasu City Aquatic Center",
        sub_intent="TIME_LOOKUP",
    )
    assert ans is None


def test_about_shape_still_declines(db):
    _seed_event(db, title="Open Swim", location_name="Lake Havasu Aquatic Center")
    ans = try_intent_layer(
        "tell me about the aquatic center",
        db,
        entity="Lake Havasu City Aquatic Center",
        sub_intent="OPEN_ENDED",
    )
    assert ans is None


def test_unrelated_venue_does_not_match(db):
    _seed_event(db, title="Trivia Night", location_name="Mudshark Brewery")
    ans = try_intent_layer(
        "what events does the aquatic center have",
        db,
        entity="Lake Havasu City Aquatic Center",
        sub_intent="OPEN_ENDED",
    )
    assert ans is None  # Mudshark's event must not leak into the aquatic center
