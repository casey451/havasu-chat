"""Lane B5 — itinerary builder: populated day, honest empty slot, time order."""

from __future__ import annotations

from datetime import date, time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Event, Provider
from app.events.queries import event_window_for_chip
from app.main import app
from app.plan.builder import build_itinerary


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _make_provider(db, *, suf: str, name: str, category: str, subcategory: str,
                   rating: float | None = 4.5) -> str:
    eid = str(uuid4())
    db.add(
        Entity(
            id=eid,
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"plan-ent-{suf}",
            name=name,
            source="test-plan",
        )
    )
    prov = Provider(
        provider_name=name,
        category=category,
        subcategory=subcategory,
        source="test-plan",
        slug=f"plan-prov-{suf}",
        draft=False,
        is_active=True,
        verified=False,
        entity_id=eid,
        address="123 Test St, Lake Havasu City",
        google_rating=rating,
        google_review_count=10,
    )
    db.add(prov)
    db.flush()
    return eid


def _make_event(db, *, suf: str, on_date: date, title: str, start: time) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name=f"Plan Venue {suf}",
        location_normalized=f"plan venue {suf}",
        description="Test event",
        event_url="https://example.com/plan-e",
        status="live",
        source="test-plan",
        is_recurring=False,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    db.flush()
    return ev.id


def _cleanup(entity_ids: list[str], event_ids: list[str]) -> None:
    with SessionLocal() as db:
        for evid in event_ids:
            db.query(Event).filter_by(id=evid).delete()
        for eid in entity_ids:
            db.query(Provider).filter_by(entity_id=eid).delete()
            db.query(Event).filter_by(entity_id=eid).delete()
        db.commit()
    with SessionLocal() as db2:
        for eid in entity_ids:
            db2.query(Entity).filter_by(id=eid).delete()
        db2.commit()


def test_populated_day_fills_slots() -> None:
    suf = uuid4().hex[:8]
    today = date(2026, 6, 6)  # a Saturday
    eids: list[str] = []
    evids: list[str] = []
    try:
        with SessionLocal() as db:
            eids.append(
                _make_provider(
                    db, suf=f"park{suf}", name=f"Lakeside Park {suf}",
                    category="recreation_outdoors", subcategory="parks-nature",
                )
            )
            eids.append(
                _make_provider(
                    db, suf=f"eat{suf}", name=f"Tasty Diner {suf}",
                    category="food_drink", subcategory="restaurants",
                )
            )
            eids.append(
                _make_provider(
                    db, suf=f"water{suf}", name=f"Havasu Marina {suf}",
                    category="on_the_water", subcategory="marinas-launches",
                )
            )
            evids.append(
                _make_event(
                    db, suf=suf, on_date=today, title=f"Evening Concert {suf}",
                    start=time(19, 0),
                )
            )
            db.commit()
            itinerary = build_itinerary(db, when="today", today=today)

        slots = {s.slot: s for s in itinerary.stops}
        # Lunch is grounded by category/subcategory across the whole catalog, so
        # we assert the structure + that at least the evening event we created is
        # surfaced from real data.
        assert set(slots) == {"morning", "lunch", "afternoon", "evening"}
        evening = slots["evening"]
        assert evening.filled is True
        assert evening.pick.kind == "event"
        # The evening pick is a real event with its real start time.
        assert evening.suggested_time == time(19, 0)
        assert itinerary.has_any is True
    finally:
        _cleanup(eids, evids)


def test_empty_slot_is_honest_no_fabrication() -> None:
    # A far-future day with no catalog events -> the evening slot cannot invent
    # an event; whatever it shows is either a real provider or an honest empty.
    today = date(2031, 3, 8)  # Saturday, far future
    with SessionLocal() as db:
        itinerary = build_itinerary(db, when="today", today=today)

    evening = {s.slot: s for s in itinerary.stops}["evening"]
    # No catalog event this far out -> never an event pick.
    if evening.pick is not None:
        assert evening.pick.kind == "provider"  # only real providers, never invented
    for stop in itinerary.stops:
        if not stop.filled:
            assert stop.pick is None
            assert stop.empty_message  # honest message present
            assert stop.contribute_href == "/contribute"


def test_stops_are_time_ordered() -> None:
    today = date(2026, 6, 6)
    with SessionLocal() as db:
        itinerary = build_itinerary(db, when="today", today=today)
    keys = [s.sort_key for s in itinerary.stops]
    assert keys == sorted(keys)
    # Morning must precede lunch must precede afternoon in the suggested rhythm.
    slot_order = [s.slot for s in itinerary.stops]
    assert slot_order.index("morning") < slot_order.index("lunch")
    assert slot_order.index("lunch") < slot_order.index("afternoon")


def test_api_plan_returns_structured_itinerary(client: TestClient) -> None:
    r = client.post("/api/plan", json={"when": "today"})
    assert r.status_code == 200
    body = r.json()
    assert "plan_date" in body and "stops" in body
    assert len(body["stops"]) == 4
    for stop in body["stops"]:
        assert set(stop) >= {"slot", "label", "suggested_time", "filled", "pick"}
        if not stop["filled"]:
            assert stop["pick"] is None
            assert stop["empty_message"]


def test_plan_page_renders(client: TestClient) -> None:
    r = client.get("/plan?when=today")
    assert r.status_code == 200
    assert "Your day in Havasu" in r.text


def test_weekend_anchors_on_saturday() -> None:
    today = date(2026, 6, 1)  # Monday
    with SessionLocal() as db:
        itinerary = build_itinerary(db, when="this_weekend", today=today)
    start, end = event_window_for_chip("this-weekend", today=today)
    saturday = start + timedelta(days=(5 - start.weekday()) % 7)
    expected = saturday if start <= saturday <= end else start
    assert itinerary.plan_date == expected
    assert "weekend" in itinerary.title.lower()
