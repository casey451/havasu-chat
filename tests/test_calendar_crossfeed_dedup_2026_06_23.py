"""Cross-feed calendar dedup — Event ↔ recurring-Class twins render once.

Phase 1.1 (FIX_SPEC_2026-06-23 / UX review §P0). The live 2026-06-23 capture
showed activities twice — once as a one-off ``EVENT`` and once as a recurring
``CLASS`` ("Runs regularly"), with title variants like ``Lap Swim`` vs
``Lap Swim (Morning)`` and the Senior Center ``Exercise Class`` doubled.

Tracing the symptom into code showed the cross-feed dedup is **already present
and correct**: both ``day_groups`` (events_views.py:437) and ``week_rows``
(:564) run ``drop_event_duplicates(class_occurrences_in_window(...), event_keys)``
keyed on ``(normalized-title, date, start_time)``, and ``_dedup_title_tokens``
already strips parentheticals/clock/weekday tokens. So the live doubling was the
stale deploy (matches Phase 0 A–G). These tests lock the fix at the layer the
existing suite didn't yet cover: a **parenthetical title variant** twin rendered
end-to-end through ``/events-ui`` (the unit tests cover the helper in isolation;
``test_events_ui_skips_class_that_is_also_an_event`` covers only an exact-title
twin).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Event, Provider, Schedule
from app.home import events_views
from app.main import app


def _rendered_rows(groups: list[dict]) -> list[dict]:
    """Rows the template renders: subgroup rows when split, else flat rows."""
    rows: list[dict] = []
    for g in groups:
        subs = g.get("subgroups") or []
        rows += [r for sub in subs for r in sub["rows"]] if subs else (g.get("rows") or [])
    return rows


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _seed_event_and_class_twin(
    base_title: str, *, when: date, weekday: str, start: time, venue: str
) -> None:
    """Seed a one-off Event ``base_title`` and a recurring Schedule class
    ``"{base_title} (Morning)"`` at the same venue/day/time — the live twin
    shape. They must collapse to one rendered row."""
    with SessionLocal() as db:
        prov = Provider(
            provider_name=venue, category="fitness_sports",
            verified=True, draft=False, is_active=True, pending_review=False,
            source="test-crossfeed-dedup",
        )
        db.add(prov)
        db.commit()
        eid = prov.entity_id
        db.add(
            Schedule(
                entity_id=eid, schedule_type="recurring", days_of_week=[weekday],
                start_time=start, end_time=None, notes=f"{base_title} (Morning)",
                created_at=_now(), updated_at=_now(),
            )
        )
        db.add(
            Event(
                title=base_title, normalized_title=base_title.lower(),
                date=when, start_time=start,
                location_name=venue, location_normalized=venue.lower(),
                description="The event-table twin of the recurring class.",
                source="parks_rec", tags=["class"], status="live",
            )
        )
        db.commit()


def test_parenthetical_variant_twin_renders_once_on_events_ui() -> None:
    base = f"Lap Swim {uuid.uuid4().hex[:6]}"
    when = date(2026, 12, 4)  # a Friday
    _seed_event_and_class_twin(
        base, when=when, weekday="friday", start=time(5, 0),
        venue="Aquatic Center Crossfeed",
    )
    # Two-surface split (spec §1): Lap Swim activity-classifies as a class, so
    # the twin pair lives on Places & Ongoing. The cross-feed dedup
    # (drop_event_duplicates) still suppresses the "(Morning)" class twin in the
    # builder's mixed mode — exactly ONE row carries the base title.
    with SessionLocal() as db:
        groups = events_views.day_groups(db, day=when, events_only=False)
    rows = _rendered_rows(groups)
    assert sum(1 for r in rows if (r.get("title") or "") == base) == 1


def test_senior_center_exercise_class_twin_renders_once() -> None:
    """The UX review's headline example: 8:30 AM Exercise Class shown as both an
    EVENT and a CLASS at the Senior Center on the same slot."""
    base = f"Exercise Class {uuid.uuid4().hex[:6]}"
    when = date(2026, 12, 7)  # a Monday
    _seed_event_and_class_twin(
        base, when=when, weekday="monday", start=time(8, 30),
        venue="Lake Havasu Senior Center Crossfeed",
    )
    r = TestClient(app).get(f"/events-ui?date={when.isoformat()}")
    assert r.status_code == 200
    assert r.text.count(f'et">{base}<') == 1
