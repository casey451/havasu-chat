"""Calendar taxonomy rebuild — iCal CATEGORIES (Phase 6).

The /events.ics feed now emits a CATEGORIES line per VEVENT: the top-level
bucket label + the canonical activity slug (from the activity:<slug> tag stamped
at ingest, or the shared classifier), with a coarse-tag fallback so markets /
civic / music rows are still categorized.
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

from app.api.routes.calendar_feed import _event_categories, build_single_event_ics
from app.db.database import SessionLocal
from app.db.models import Event
from app.schemas.event import EventCreate


def _ev(title: str, tags: list[str], venue: str | None = "Somewhere") -> SimpleNamespace:
    return SimpleNamespace(title=title, location_name=venue, tags=tags)


def test_categories_for_activity_rows() -> None:
    assert _event_categories(_ev("Stained Glass", ["activity:arts"])) == [
        "Classes & Workshops", "arts",
    ]
    assert _event_categories(_ev("Toptracer Range", ["activity:golf"])) == [
        "Fitness & Sports", "golf",
    ]
    # Tag-less arts title still classifies via the shared classifier.
    assert _event_categories(_ev("Polymer Clay Jewelry", [])) == [
        "Classes & Workshops", "arts",
    ]


def test_categories_coarse_fallback_for_nonactivity_rows() -> None:
    assert _event_categories(_ev("Live Band Night", ["music"])) == ["Music & Nightlife"]
    assert _event_categories(_ev("City Council Meeting", ["civic"])) == ["City & Government"]
    assert _event_categories(_ev("Farmers Market", ["market"])) == ["Markets & Shopping"]
    # Nothing classifiable -> no CATEGORIES (the feed omits the line).
    assert _event_categories(_ev("Mystery Gathering", [])) == []


def test_ics_feed_emits_categories_line() -> None:
    payload = EventCreate(
        title="Stained Glass Workshop",
        date=date(2026, 6, 18),
        end_date=None,
        start_time=time(18, 30, 0),
        end_time=time(20, 0, 0),
        location_name="Havasu Art Guild",
        description="Make a stained glass piece.",
        event_url="https://example.com/glass",
        tags=["activity:arts", "arts"],
        embedding=None,
        status="live",
        created_by="user",
        admin_review_by=None,
    )
    with SessionLocal() as db:
        ev = Event.from_create(payload)
        db.add(ev)
        db.commit()
        db.refresh(ev)
        ics = build_single_event_ics(ev)
    assert "CATEGORIES:Classes & Workshops,arts" in ics
