"""Phase 9a — event card freshness + occurrence rendering."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Event
from app.providers import queries as provider_queries


def _make_event(db, **kwargs) -> Event:
    title = kwargs.pop("title", f"Card {uuid.uuid4().hex[:6]}")
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=kwargs.pop("date", date(2026, 12, 1)),
        start_time=kwargs.pop("start_time", time(18, 0)),
        location_name="Loc",
        location_normalized="loc",
        description="D",
        event_url="https://example.com",
        status=kwargs.pop("status", "live"),
        source="test",
        **kwargs,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    db.commit()
    return ev


def test_derive_event_freshness_band_tighter_than_entity() -> None:
    now = datetime(2026, 5, 23, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    ev = Event(
        title="F",
        normalized_title="f",
        date=date(2026, 6, 1),
        start_time=time(10, 0),
        location_name="L",
        location_normalized="l",
        description="d",
        scraped_at=now - timedelta(days=10),
    )
    assert provider_queries.derive_event_freshness_band(ev, now=now) == "amber"
    assert (
        provider_queries.derive_freshness_band_from_updated_at(now - timedelta(days=10), now=now)
        == "green"
    )


def test_cancelled_status_line_red() -> None:
    now = datetime(2026, 5, 23, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    ev = Event(
        title="X",
        normalized_title="x",
        date=date(2026, 6, 1),
        start_time=time(10, 0),
        location_name="L",
        location_normalized="l",
        description="d",
        status="cancelled",
    )
    text, color = provider_queries._event_status_line_for_card(ev, now=now)
    assert text == "Cancelled"
    assert color == "red"


def test_occurrence_date_drives_status_line() -> None:
    now = datetime(2026, 5, 23, 18, 0, tzinfo=LAKE_HAVASU_TZ)
    ev = Event(
        title="X",
        normalized_title="x",
        date=date(2026, 1, 1),
        start_time=time(19, 0),
        location_name="L",
        location_normalized="l",
        description="d",
        status="live",
    )
    text, _ = provider_queries._event_status_line_for_card(ev, now=now, occurrence_date=now.date())
    assert "Tonight" in text


def test_build_card_view_model_for_event_occurrence() -> None:
    with SessionLocal() as db:
        ev = _make_event(
            db,
            date=date(2026, 6, 10),
            rrule="FREQ=WEEKLY;BYDAY=WE",
            is_recurring=True,
        )
        vm = provider_queries.build_card_view_model_for_event_occurrence(
            db,
            ev.id,
            date(2026, 6, 17),
            now=datetime(2026, 6, 15, 12, 0, tzinfo=LAKE_HAVASU_TZ),
        )
        assert vm is not None
        assert "Wednesday" in vm.status_line_text or "Jun" in vm.status_line_text
        db.delete(ev)
        db.commit()
