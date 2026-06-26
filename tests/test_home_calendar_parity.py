"""Home feed ↔ /events-ui Calendar parity (Rule 0, 2026-06-26).

The #1 recurring failure was the home feed and the main calendar drifting apart
(CC editing /events-ui and forgetting the home feed). They now share ONE builder
— ``events_views.calendar_day_view_model`` — and ``redesign.feed_view_model``
consumes it without reshaping the tree. This test asserts the
(section, subgroup, youth/facet child, count, order) tuples are IDENTICAL across
both consumers for a seeded day, so editing one path without the other fails CI.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event, MovieShowtime
from app.home import events_views as ev
from app.home import redesign

_SRC = "_home_parity_probe"
_DAY = date(2099, 9, 14)  # far-future, deterministic


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe(db: Session):
    db.query(Event).filter(Event.source == _SRC).delete()
    db.query(MovieShowtime).filter(MovieShowtime.source == _SRC).delete()
    db.commit()
    yield
    db.query(Event).filter(Event.source == _SRC).delete()
    db.query(MovieShowtime).filter(MovieShowtime.source == _SRC).delete()
    db.commit()


def _add(db: Session, *, title: str, tags: list[str]) -> None:
    db.add(
        Event(
            title=title, normalized_title=title.lower(), date=_DAY,
            start_time=time(18, 0), end_time=time(20, 0),
            location_name="Venue", location_normalized="venue",
            description="x", event_url="https://example.com/e", tags=tags,
            status="live", source=_SRC, verified=True,
        )
    )


def _tree_sig(sections: list[dict]) -> list:
    """The structural signature: (key, count, [(sublabel, subcount, [(child, n)])])."""
    out = []
    for s in sections:
        subs = []
        for sub in s.get("subgroups", []) or []:
            children = [(c["label"], c["count"]) for c in sub.get("children", []) or []]
            subs.append((sub["label"], sub["count"], tuple(children)))
        out.append((s["key"], s["count"], tuple(subs)))
    return out


def test_home_feed_matches_events_ui_calendar(db: Session) -> None:
    # A spread across sections/subgroups so the signature is non-trivial.
    _add(db, title="ZZ Parade Festival", tags=["events", "festival"])
    _add(db, title="ZZ Community Bingo Night", tags=["events", "activity:games"])
    _add(db, title="ZZ City Council Meeting", tags=["civic", "government", "meeting"])
    _add(db, title="ZZ The Brew Band Live Music", tags=["music"])
    _add(db, title="ZZ Rock & Bowl Night", tags=["activity:bowling", "facet:special"])
    db.add(
        MovieShowtime(
            source=_SRC, source_stable_id=f"p-{uuid.uuid4().hex[:6]}",
            theater_slug="star-cinemas", theater_name="Star Cinemas",
            film_title="ZZ Parity Film", show_date=_DAY, show_time=time(19, 0),
            booking_url="https://example.com/book",
        )
    )
    db.commit()

    calendar = ev.calendar_day_view_model(db, day=_DAY)["sections"]
    feed = redesign.feed_view_model(db, day=_DAY)["sections"]

    # The home feed must render the IDENTICAL nested tree as /events-ui.
    assert _tree_sig(feed) == _tree_sig(calendar)
    # And it must be a real, multi-section tree (guards against an empty pass).
    assert len(calendar) >= 4
    keys = [s["key"] for s in calendar]
    assert "events" in keys and "movies" in keys and "civic" in keys
