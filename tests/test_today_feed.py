"""Phase 2 — the home unified "Today in Lake Havasu" feed builder.

Verifies the four-group remap (Events / Classes & fitness / Open all day / At
the movies), the audience tags, the cross-source de-dup (one row per real-world
occurrence), and the per-film movie grouping. Seeding mirrors
tests/test_events_ui_views.py: far-future dates + uuid suffixes + targeted
cleanup, and an explicit ``now`` so the same-day expiry never trims the rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event, MovieShowtime
from app.home.today_feed import today_feed

_LHC = ZoneInfo("America/Phoenix")
# 2099-07-13 is a Monday (see tests/test_events_ui_views.py).
_DAY = date(2099, 7, 13)
_NOW = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)  # early, so evening rows live


def _add_event(
    db, *, title, on=_DAY, start, loc, tags=None, recurring=False, source="test-today-feed"
) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=None,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=tags or [],
        status="live",
        source=source,
        verified=True,
        is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _add_movie(db, *, film, sid, theater_slug="star-cinemas", theater_name="Star Cinemas",
               at=time(18, 30)) -> str:
    row = MovieShowtime(
        source="test-today-feed",
        source_stable_id=sid,
        theater_slug=theater_slug,
        theater_name=theater_name,
        film_title=film,
        show_date=_DAY,
        show_time=at,
        booking_url="https://example.com/book",
    )
    db.add(row)
    db.flush()
    return row.id


def _cleanup(eids: list[str], mids: list[str]) -> None:
    with SessionLocal() as db:
        if eids:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
        if mids:
            db.execute(delete(MovieShowtime).where(MovieShowtime.id.in_(mids)))
        db.commit()


def _group(feed: dict, key: str) -> dict | None:
    return next((g for g in feed["groups"] if g["key"] == key), None)


def _titles(group: dict | None) -> list[str]:
    return [r["title"] for r in group["rows"]] if group else []


def test_feed_classifies_into_four_groups() -> None:
    s = uuid.uuid4().hex[:6]
    market = f"ZZ Farmers Market {s}"        # happening w/ time  -> events
    yoga = f"ZZ Sunrise Yoga Flow {s}"       # class keyword      -> classes
    pickle = f"ZZ Pickleball Open Play {s}"  # all-day drop-in    -> open_all_day
    film = f"ZZ Robin Hood {s}"              # movie              -> movies
    eids: list[str] = []
    mids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=market, start=time(8, 0), loc="Visitor Center"))
        eids.append(_add_event(db, title=yoga, start=time(18, 0), loc="Eight Lotus"))
        # All-day drop-in convention: midnight start + no end reads as "all day".
        eids.append(_add_event(db, title=pickle, start=time(0, 0), loc="Ark Center"))
        mids.append(_add_movie(db, film=film, sid=f"m-{s}"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        assert market in _titles(_group(feed, "events"))
        assert yoga in _titles(_group(feed, "classes"))
        assert pickle in _titles(_group(feed, "open_all_day"))
        movies = _group(feed, "movies")
        assert movies and any(f["title"] == film for f in movies["films"])
        # The summary line names each non-empty group.
        assert "open all day" in feed["summary"]
        # Group display order: events, classes, open_all_day, movies.
        keys = [g["key"] for g in feed["groups"]]
        assert keys == sorted(keys, key=["events", "classes", "open_all_day", "movies"].index)
        # Events opens by default; nothing else does.
        assert _group(feed, "events")["open"] is True
        assert _group(feed, "classes")["open"] is False
    finally:
        _cleanup(eids, mids)


def test_feed_dedupes_cross_source_twin() -> None:
    """Two scrapers carrying one real-world event (same title+date+time) collapse
    to a single feed row — the de-dup the redesign requires, in the data layer."""
    s = uuid.uuid4().hex[:6]
    title = f"ZZ Lake Cleanup {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=title, start=time(9, 0), loc="Beach", source="src-a"))
        eids.append(_add_event(db, title=title, start=time(9, 0), loc="Beach", source="src-b"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        events = _group(feed, "events")
        assert _titles(events).count(title) == 1
    finally:
        _cleanup(eids, [])


def test_feed_audience_tags() -> None:
    s = uuid.uuid4().hex[:6]
    kids = f"ZZ Kids Craft Hour {s}"
    senior = f"ZZ Senior Bingo {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=kids, start=time(10, 0), loc="Library"))
        eids.append(_add_event(db, title=senior, start=time(11, 0), loc="Senior Center"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        rows = {r["title"]: r for g in feed["groups"] if g["key"] != "movies" for r in g["rows"]}
        assert "Kids" in rows[kids]["tags"]
        assert "Seniors" in rows[senior]["tags"]
    finally:
        _cleanup(eids, [])


def test_feed_movie_groups_theaters_per_film() -> None:
    """One film at two theaters collapses to a single film row with both theaters
    in its expand."""
    s = uuid.uuid4().hex[:6]
    film = f"ZZ Two-Theater Flick {s}"
    mids: list[str] = []
    with SessionLocal() as db:
        mids.append(_add_movie(db, film=film, sid=f"sc-{s}",
                               theater_slug="star-cinemas", theater_name="Star Cinemas",
                               at=time(12, 40)))
        mids.append(_add_movie(db, film=film, sid=f"mh-{s}",
                               theater_slug="movies-havasu", theater_name="Movies Havasu",
                               at=time(13, 0)))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        movies = _group(feed, "movies")
        card = next(f for f in movies["films"] if f["title"] == film)
        assert len(card["theaters"]) == 2
        assert "2 theaters" in card["summary"]
    finally:
        _cleanup([], mids)


def test_feed_empty_day_has_no_groups() -> None:
    with SessionLocal() as db:
        feed = today_feed(db, day=date(2099, 7, 14), now=datetime(2099, 7, 14, 6, 0, tzinfo=_LHC))
    # A far-future Tuesday with nothing seeded: no event groups. (Venue "open
    # today" rows are weekday-driven and may exist, but the seeded-data groups
    # above are what we assert on; here we assert no events/classes/movies.)
    assert _group(feed, "events") is None
    assert _group(feed, "classes") is None
    assert _group(feed, "movies") is None
