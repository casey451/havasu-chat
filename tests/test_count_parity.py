"""v4.4 PR-3 — one day-count base across every summary surface (DATA_CONTRACTS §2).

F6 symptom: the home headline, the calendar agenda header, and a calendar cell
each counted a day differently (home 54, agenda 17, cell implying 87). This pins
that the home feed total, the agenda "N events & classes" header, and
``day_counts(d).total`` are one and the same number, and that the base equals the
canonical day builder's total.
"""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import events_views, redesign
from app.home.day_counts import day_counts


def test_day_counts_total_equals_canonical_builder() -> None:
    d = date(2026, 7, 15)
    with SessionLocal() as db:
        vm = events_views.calendar_day_view_model(db, day=d)
        dc = day_counts(db, d, vm=vm)
        assert dc.total == vm["total"]
        assert dc.by_group == {s["key"]: int(s.get("count") or 0) for s in vm["sections"]}
        # the by-group counts sum to the total (no orphan base)
        assert sum(dc.by_group.values()) == dc.total


def test_vm_passthrough_avoids_second_build() -> None:
    # With a supplied vm, day_counts must not touch the db (db=None proves it).
    fake_vm = {"total": 7, "sections": [{"key": "events", "count": 5},
                                        {"key": "classes", "count": 2}]}
    dc = day_counts(None, date(2026, 7, 15), vm=fake_vm)  # type: ignore[arg-type]
    assert dc.total == 7
    assert dc.by_group == {"events": 5, "classes": 2}


def test_home_agenda_and_daycount_agree_on_a_seeded_day() -> None:
    d = date(2026, 10, 12)
    titles = ["ZZ Parity Alpha", "ZZ Parity Beta", "ZZ Parity Gamma"]
    ids: list[tuple[str, str | None]] = []
    with SessionLocal() as db:
        for i, t in enumerate(titles):
            ev = Event(
                title=t, normalized_title=t.lower(), date=d,
                start_time=time(9 + i, 0), end_time=None, location_name="Rotary Park",
                location_normalized="rotary park", description="probe",
                event_url=f"https://example.com/{i}", source_url="", tags=[],
                status="live", source="test", verified=True, is_recurring=False,
            )
            db.add(ev)
            db.commit()
            ids.append((ev.id, ev.entity_id))
    try:
        with SessionLocal() as db:
            dc = day_counts(db, d)
            feed = redesign.feed_view_model(db, day=d)
            agenda = redesign._agenda(db, d)
        # The three summary surfaces report the SAME base.
        assert feed["total"] == dc.total
        assert agenda["total"] == dc.total
        assert dc.total >= len(titles)  # our seeded events are counted
    finally:
        with SessionLocal() as db:
            ev_ids = [i for i, _ in ids]
            ent_ids = [e for _, e in ids if e]
            db.execute(delete(Event).where(Event.id.in_(ev_ids)))
            if ent_ids:
                db.execute(delete(Entity).where(Entity.id.in_(ent_ids)))
            db.commit()
