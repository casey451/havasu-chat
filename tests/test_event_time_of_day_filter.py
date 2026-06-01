"""Time-of-day event intent + events_in_window filter tests (CLUSTER-02)."""

from __future__ import annotations

from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete

from app.chat.component_builders import build_day_agenda
from app.chat.tier2_handler import _event_rows_for_intent, detect_event_intent, try_tier2_with_usage
from app.chat.tier2_schema import Tier2Filters
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Category, EntityCategory, Event
from app.events.queries import events_in_window

_LHC = ZoneInfo("America/Phoenix")


def test_detect_tonight_includes_evening_bounds() -> None:
    assert detect_event_intent("what's happening tonight") == {
        "when": "tonight",
        "time_start": "17:00",
        "time_end": "23:59",
    }


def test_detect_whats_on_today_has_no_time_bounds() -> None:
    assert detect_event_intent("what's on today") == {"when": "today"}


def test_detect_this_morning_bounds() -> None:
    assert detect_event_intent("what's on this morning") == {
        "when": "today",
        "time_start": "05:00",
        "time_end": "11:59",
    }


def test_detect_this_afternoon_bounds() -> None:
    assert detect_event_intent("events this afternoon") == {
        "when": "today",
        "time_start": "12:00",
        "time_end": "16:59",
    }


def test_event_start_in_time_window_helpers() -> None:
    from app.events.queries import _event_start_in_time_window, _parse_hhmm_bound

    assert _parse_hhmm_bound("17:00") == (17, 0)
    assert _event_start_in_time_window(time(18, 30), (17, 0), (23, 59)) is True
    assert _event_start_in_time_window(time(6, 0), (17, 0), (23, 59)) is False
    assert _event_start_in_time_window(None, (17, 0), (23, 59)) is False
    assert _event_start_in_time_window(time(12, 0), None, None) is True


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


def _events_category_id(db) -> int:
    row = db.query(Category).filter(Category.slug == "events").first()
    assert row is not None
    return row.id


def _make_event(db, *, title: str, on_date: date, start: time) -> Event:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name="Aquatic Center",
        location_normalized="aquatic center",
        description="Test",
        event_url="https://example.com/e",
        status="live",
        source="test_time_filter",
        is_recurring=False,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    cat_id = _events_category_id(db)
    db.add(
        EntityCategory(
            entity_id=ev.entity_id,
            category_id=cat_id,
            is_primary=True,
        )
    )
    db.flush()
    return ev


def test_events_in_window_filters_tonight_hours(db) -> None:
    day = date(2026, 5, 28)
    morning = _make_event(db, title="Morning Swim", on_date=day, start=time(6, 0))
    evening = _make_event(db, title="Evening Jazz", on_date=day, start=time(19, 0))
    db.commit()
    try:
        all_day = events_in_window(db, window_start=day, window_end=day, limit=20)
        titles_all = {ev.title for ev, _ in all_day}
        assert "Morning Swim" in titles_all
        assert "Evening Jazz" in titles_all

        tonight = events_in_window(
            db,
            window_start=day,
            window_end=day,
            time_start="17:00",
            time_end="23:59",
            limit=20,
        )
        titles_tonight = {ev.title for ev, _ in tonight}
        assert "Morning Swim" not in titles_tonight
        assert "Evening Jazz" in titles_tonight
    finally:
        for ev in (morning, evening):
            db.execute(delete(Event).where(Event.id == ev.id))
        db.commit()


def test_events_in_window_dedupes_same_event(db) -> None:
    day = date(2026, 5, 28)
    ev = _make_event(db, title="Dup Test", on_date=day, start=time(19, 0))
    db.commit()
    try:
        with patch("app.events.queries.occurrences_in_window") as mock_occ:
            mock_occ.return_value = [(ev, day), (ev, day)]
            flat = events_in_window(db, window_start=day, window_end=day, limit=10)
        assert len(flat) == 1
    finally:
        db.execute(delete(Event).where(Event.id == ev.id))
        db.commit()


def test_build_day_agenda_dedupes_duplicate_rows() -> None:
    rows = [
        {
            "type": "event",
            "name": "Lap Swim",
            "date": "2026-05-28",
            "start_time": "05:00",
            "location_name": "Aquatic Center",
            "tags": ["aquatics"],
        },
        {
            "type": "event",
            "name": "Lap Swim",
            "date": "2026-05-28",
            "start_time": "05:00",
            "location_name": "Aquatic Center",
            "tags": ["aquatics"],
        },
        {
            "type": "event",
            "name": "Yoga",
            "date": "2026-05-28",
            "start_time": "18:00",
            "location_name": "Community Center",
            "tags": ["fitness"],
        },
    ]
    filters = Tier2Filters(time_window="today", parser_confidence=0.9)
    data = build_day_agenda(filters, rows)
    titles = [ev["title"] for ev in data["events"]]
    assert titles.count("Lap Swim") == 1
    assert "Yoga" in titles


def test_event_rows_for_intent_passes_time_bounds() -> None:
    intent = {"when": "tonight", "time_start": "17:00", "time_end": "23:59"}
    with patch("app.chat.tier2_handler.events_in_window") as mock_win:
        mock_win.return_value = []
        _event_rows_for_intent(intent)
    mock_win.assert_called_once()
    _, kwargs = mock_win.call_args
    assert kwargs["time_start"] == "17:00"
    assert kwargs["time_end"] == "23:59"


def _fixed_lhc_now() -> datetime:
    """Isolated test day — unlikely to collide with seeded catalog rows."""
    return datetime(2099, 1, 15, 13, 48, tzinfo=_LHC)


def _test_day() -> date:
    return date(2099, 1, 15)


def test_tonight_query_empty_when_only_morning_events(db) -> None:
    """Regression: zero evening rows must not fall through to all-day LLM path."""
    day = _test_day()
    morning = _make_event(db, title="Morning Swim", on_date=day, start=time(6, 0))
    db.commit()
    component_meta: dict = {}
    try:
        with patch("app.chat.tier2_handler.now_lake_havasu", return_value=_fixed_lhc_now()):
            with patch(
                "app.chat.tier2_handler.tier2_parser.parse",
                side_effect=AssertionError("must not fall through to LLM parser"),
            ):
                voice, total, in_t, out_t = try_tier2_with_usage(
                    "what's on tonight",
                    component_meta=component_meta,
                )
        assert voice == 'Nothing on tonight — try "what\'s on tomorrow".'
        assert total == 0 and in_t == 0 and out_t == 0
        assert component_meta.get("type") == "day_agenda"
        assert component_meta.get("data", {}).get("events") == []
    finally:
        db.execute(delete(Event).where(Event.id == morning.id))
        db.commit()


def test_tonight_query_excludes_morning_events(db) -> None:
    day = _test_day()
    morning = _make_event(db, title="Morning Swim", on_date=day, start=time(6, 0))
    evening = _make_event(db, title="Evening Jazz", on_date=day, start=time(19, 0))
    db.commit()
    component_meta: dict = {}
    try:
        with patch("app.chat.tier2_handler.now_lake_havasu", return_value=_fixed_lhc_now()):
            voice, total, _, _ = try_tier2_with_usage(
                "what's on tonight",
                component_meta=component_meta,
            )
        assert total == 0
        assert component_meta.get("type") == "day_agenda"
        events = component_meta.get("data", {}).get("events", [])
        titles = {ev["title"] for ev in events}
        assert "Morning Swim" not in titles
        assert "Evening Jazz" in titles
        for ev in events:
            hour = int(str(ev.get("start") or "99").split(":")[0])
            assert hour >= 17
        assert "Evening Jazz" in voice or "one" in voice
    finally:
        for ev in (morning, evening):
            db.execute(delete(Event).where(Event.id == ev.id))
        db.commit()


def test_whats_on_today_still_returns_full_day(db) -> None:
    day = _test_day()
    morning = _make_event(db, title="Morning Swim", on_date=day, start=time(6, 0))
    evening = _make_event(db, title="Evening Jazz", on_date=day, start=time(19, 0))
    db.commit()
    component_meta: dict = {}
    try:
        with patch("app.chat.tier2_handler.now_lake_havasu", return_value=_fixed_lhc_now()):
            _, total, _, _ = try_tier2_with_usage(
                "what's on today",
                component_meta=component_meta,
            )
        assert total == 0
        assert component_meta.get("type") == "day_agenda"
        titles = {ev["title"] for ev in component_meta.get("data", {}).get("events", [])}
        assert "Morning Swim" in titles
        assert "Evening Jazz" in titles
    finally:
        for ev in (morning, evening):
            db.execute(delete(Event).where(Event.id == ev.id))
        db.commit()
