"""Empty-url class rows render as plain text, never <a href="">.

Phase 2.2 (FIX_SPEC_2026-06-23). Live bug: page-less class rows (e.g. Havasu
Pilates) linked back to ``/events-ui`` — a browser resolves ``href=""`` to the
current URL. Tracing into code shows it's already handled: ``ClassOccurrence.url``
returns ``""`` when there is no provider slug/website, and BOTH events templates
(``events_lake.html:78-82``, ``events_sandstone.html:69-85``) wrap such rows in a
``--nolink`` ``<div>``, not an ``<a>``. The live self-link was the stale deploy.
These regressions lock the render-time guard on both themes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Entity, Schedule
from app.main import app


def _seed_pageless_program(title: str, weekday: str) -> None:
    """Active venue Entity + recurring Schedule but NO Provider and no curated
    website → occ.url == "" (the page-less program shape)."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        ent = Entity(
            entity_type="venue", slug=f"pageless-{suf}",
            name=f"Pageless Program Venue {suf}",
            source="test-class-row-links", is_active=True,
        )
        db.add(ent)
        db.commit()
        db.add(
            Schedule(
                entity_id=ent.id, schedule_type="recurring", days_of_week=[weekday],
                start_time=time(9, 0), end_time=time(10, 0), notes=title,
                created_at=datetime.now(UTC).replace(tzinfo=None),
                updated_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()


def _assert_pageless_row_is_not_a_dead_link(theme_qs: str) -> None:
    title = f"Pageless Pilates {uuid.uuid4().hex[:6]}"
    when = date(2026, 12, 9)  # a Wednesday
    _seed_pageless_program(title, "wednesday")
    r = TestClient(app).get(f"/events-ui?date={when.isoformat()}{theme_qs}")
    assert r.status_code == 200
    assert title in r.text, "page-less program should still render on the day page"
    # The exact live bug: an empty/self href the browser resolves to /events-ui.
    assert 'href=""' not in r.text
    assert 'href="#"' not in r.text


def test_pageless_class_row_has_no_dead_link_lake() -> None:
    _assert_pageless_row_is_not_a_dead_link("&theme=lake")


def test_pageless_class_row_has_no_dead_link_sandstone() -> None:
    _assert_pageless_row_is_not_a_dead_link("&theme=desert")
