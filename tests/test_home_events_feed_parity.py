"""WS1/B6 regression — ``/home`` and ``/events-ui`` must render the SAME feed.

The 2026-07-06 acceptance audit (B6) alleged the two surfaces disagreed on the
same day — a section present on one, absent on the other; a film attributed to
different theaters. That does not reproduce: both routes render the identical
section tree because ``app.home.redesign.feed_view_model`` takes its sections
straight from ``app.home.events_views.calendar_day_view_model`` (the builder
``/events-ui`` calls directly) and only *enriches* rows. See the parity note in
``feed_view_model``'s docstring ("the home and the main calendar can't drift").

This test pins that contract at the HTTP boundary so a future refactor can't
silently fork the two builders (or a template) back apart: for one seeded day,
the ``(section label, count)`` sequence rendered by ``/home?date=D`` must equal
the one rendered by ``/events-ui?date=D``.

Dates use far-future 2099 for xdist isolation (same pattern as
``tests/test_events_ui_freshness.py``).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.main import app

# A fixed future weekday well clear of "today" in any run.
_DAY = date(2099, 7, 6)

# The section macro (app/templates/components/feed_macros.html) renders each
# section header as `<span class="sl">LABEL</span> ... <span class="sc num">N</span>`.
# `class="sl serif"` is the *empty-state* label, which this regex deliberately
# excludes (seeded events guarantee non-empty sections anyway).
_LABEL_RE = re.compile(r'class="sl">([^<]+)</span>')
_COUNT_RE = re.compile(r'class="sc num">([^<]+)</span>')


def _add_event(db, *, title: str, start: time, loc: str) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=_DAY,
        start_time=start,
        end_time=None,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="test-feed-parity",
        verified=True,
        is_recurring=False,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _seed() -> list[str]:
    """A few one-off events on the target day, distinct enough to populate a
    section with a non-trivial count."""
    suffix = uuid.uuid4().hex[:6]
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=f"ZZ Parity Fair {suffix}", start=time(9, 0), loc="Rotary Park"))
        eids.append(_add_event(db, title=f"ZZ Parity Market {suffix}", start=time(10, 0), loc="Main St"))
        eids.append(_add_event(db, title=f"ZZ Parity Concert {suffix}", start=time(18, 0), loc="The Bridge"))
        db.commit()
    return eids


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def _section_pairs(html: str) -> list[tuple[str, str]]:
    labels = _LABEL_RE.findall(html)
    counts = _COUNT_RE.findall(html)
    # Every rendered section header emits exactly one label + one count span, in
    # order; if that ever stops holding the zip length guard below trips.
    assert len(labels) == len(counts), (
        f"label/count span mismatch: {len(labels)} labels vs {len(counts)} counts"
    )
    return list(zip(labels, counts))


def test_home_and_events_ui_render_identical_feed_for_a_day() -> None:
    eids = _seed()
    try:
        with TestClient(app) as client:
            home = client.get(f"/home?date={_DAY.isoformat()}")
            eui = client.get(f"/events-ui?date={_DAY.isoformat()}")
            assert home.status_code == 200
            assert eui.status_code == 200

            home_sections = _section_pairs(home.text)
            eui_sections = _section_pairs(eui.text)

            # Guard against the degenerate "both empty → trivially equal" pass.
            assert home_sections, "expected at least one rendered feed section on /home"
            # The B6 contract: same sections, same counts, same order.
            assert home_sections == eui_sections, (
                f"/home vs /events-ui feed drift:\n  home={home_sections}\n  eui ={eui_sections}"
            )
    finally:
        _cleanup(eids)
