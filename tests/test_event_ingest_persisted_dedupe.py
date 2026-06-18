"""Fix 4.4 — same-day persisted-row uniqueness guard, plus structured-field
population (cost/host/image_url) on auto-approved ingest. Uses the real
SessionLocal like the other DB-backed ingest tests in this repo.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import date, time

from app.contrib.event_ingest import ingest_event_records
from app.contrib.event_record import EventRecord


def _civic_rec(title: str, *, start_date: date, venue: str, url: str,
               description: str) -> EventRecord:
    # legistar is an auto-approve civic source, so the row is created (not left
    # pending) and we can assert on the persisted Event.
    return EventRecord(
        source="legistar",
        title=title,
        start_date=start_date,
        start_time=time(18, 0),
        venue_name=venue,
        url=url,
        description=description,
    )


def test_persisted_duplicate_guard_blocks_second_insert() -> None:
    suf = _uuid.uuid4().hex[:8]
    title = f"Planning Commission Workshop {suf}"
    venue = "City Hall Council Chambers"
    d = date(2026, 12, 4)
    first = _civic_rec(
        title, start_date=d, venue=venue,
        url=f"https://legistar.example/{suf}/a",
        description="Regular planning commission workshop session." * 2,
    )
    # Same title+date+venue, but a DIFFERENT source_url (simulates a feed glitch
    # the source_url/fuzzy reconciler might not collapse).
    second = _civic_rec(
        title, start_date=d, venue=venue,
        url=f"https://legistar.example/{suf}/DIFFERENT",
        description="Regular planning commission workshop session." * 2,
    )
    c1 = ingest_event_records([first], source="legistar", dry_run=False)
    c2 = ingest_event_records([second], source="legistar", dry_run=False)
    assert c1.auto_approved + c1.inserted_pending == 1
    # No second row: either the reconciler merged it or the persisted guard skipped.
    assert c2.auto_approved == 0
    assert (
        c2.skipped_duplicate_persisted + c2.merged_duplicate + c2.skipped_existing_pending
        == 1
    )


def test_structured_fields_populated_on_auto_approved_event() -> None:
    from app.db.database import SessionLocal
    from app.db.models import Event

    suf = _uuid.uuid4().hex[:8]
    # Unique middle token keeps the title distinct per run while the KNOWN
    # instructor name stays TRAILING (host capture only matches a trailing token,
    # mirroring real class titles like "Tai Chi Vince").
    title = f"Tai Chi {suf} Vince"
    rec = EventRecord(
        source="legistar",
        title=title,
        start_date=date(2026, 12, 5),
        start_time=time(9, 0),
        venue_name="Senior Center",
        url=f"https://legistar.example/{suf}/taichi",
        description="Gentle morning tai chi. Drop-in fee is $5 per session." * 2,
        image_url="https://cdn.example.com/taichi.jpg",
    )
    counts = ingest_event_records([rec], source="legistar", dry_run=False)
    assert counts.auto_approved == 1

    with SessionLocal() as db:
        ev = db.query(Event).filter(Event.normalized_title == title.lower()).first()
        assert ev is not None
        assert ev.host == "Vince"
        assert ev.cost == "$5"
        assert ev.image_url == "https://cdn.example.com/taichi.jpg"
