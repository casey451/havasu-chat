"""Feed-quality follow-up (live QA after #470): no dead rows, case-insensitive
movie de-dup, and the recreation classification audit.

* Item 1 — every home-feed row links to a RESOLVING destination. A venue class
  with no published provider (e.g. "Havasu Horseback Rides") used to render with
  an empty url -> the row expanded to a dead end. It now falls back to that day's
  events list.
* Item 2 — movie de-dup is case/space-insensitive across theaters.
* Item 3 — recreation / animal-rides / scenic cruises route to Things to do, not
  Classes, even when a recurring Schedule typed them as a class.

Seeding mirrors tests/test_today_feed.py (far-future dates + uuid suffixes +
targeted cleanup, explicit ``now`` so same-day expiry never trims rows).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event, MovieShowtime, Schedule
from app.home.today_feed import _home_group, today_feed

_LHC = ZoneInfo("America/Phoenix")
_DAY = date(2099, 7, 13)  # Monday
_NOW = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)  # early, so evening rows live

_ALL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _add_providerless_class(db, *, title: str, days: list[str], start=time(10, 0)) -> str:
    """An active venue Entity with a recurring class Schedule but NO Provider —
    so ``ClassOccurrence.url`` is empty (the horseback dead-row case). Returns
    the entity id."""
    suf = uuid.uuid4().hex[:8]
    ent = Entity(
        entity_type="provider",
        slug=f"horseback-{suf}",
        name=f"Havasu Horseback Rides {suf}",
        source="test-feed-quality",
        is_active=True,
    )
    db.add(ent)
    db.flush()
    db.add(
        Schedule(
            entity_id=ent.id, schedule_type="recurring", days_of_week=days,
            start_time=start, end_time=None, notes=title,
            created_at=_now_naive(), updated_at=_now_naive(),
        )
    )
    db.flush()
    return ent.id


def _add_event(db, *, title, on=_DAY, start, loc, source="test-feed-quality") -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=on, start_time=start,
        end_time=None, location_name=loc, location_normalized=loc.lower(),
        description="x", event_url="https://example.com/e", tags=[], status="live",
        source=source, verified=True, is_recurring=False,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _add_movie(db, *, film, sid, theater_slug, theater_name, at=time(18, 30)) -> str:
    row = MovieShowtime(
        source="test-feed-quality", source_stable_id=sid, theater_slug=theater_slug,
        theater_name=theater_name, film_title=film, show_date=_DAY, show_time=at,
        booking_url="https://example.com/book", is_free=False,
    )
    db.add(row)
    db.flush()
    return row.id


def _cleanup(eids: list[str], mids: list[str]) -> None:
    with SessionLocal() as db:
        if eids:
            db.execute(delete(Schedule).where(Schedule.entity_id.in_(eids)))
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
        if mids:
            db.execute(delete(MovieShowtime).where(MovieShowtime.id.in_(mids)))
        db.commit()


def _group(feed: dict, key: str):
    return next((g for g in feed["groups"] if g["key"] == key), None)


def _all_rows(feed: dict) -> list[dict]:
    """Every clickable feed row: group rows, fitness sub-rows, and movie films."""
    rows: list[dict] = []
    for g in feed["groups"]:
        if g["key"] == "movies":
            rows.extend(g.get("films", []))
        else:
            rows.extend(g.get("rows", []))
    return rows


# --- Item 3: recreation classification ------------------------------------


def test_horseback_recreation_routes_to_things_to_do_not_classes() -> None:
    """The exact live bug: a recurring, class-typed horseback row lands in Things
    to do, not Classes."""
    assert _home_group("Pony / Lead Line Rides", None, False, True, time(10, 0), None) == "things_to_do"


def test_recreation_classification_battery() -> None:
    # (tags, featured, recurring, start, end) — matches _home_group's signature
    # after the leading ``title`` argument.
    recurring_class = (None, False, True, time(10, 0), None)
    THINGS_TO_DO = [
        "Pony / Lead Line Rides",
        "Horseback Trail Ride",
        "Guided Trail Rides",
        "Sunset Lake Cruise",
        "Narrated Scenic Cruise",
        "Kayak Tour of the Channel",
        "Paddleboard Tour",
        "Jeep Off-Road Tour",
        "Sightseeing Tour",
    ]
    for title in THINGS_TO_DO:
        assert _home_group(title, *recurring_class) == "things_to_do", title


def test_classification_battery_other_buckets_unchanged() -> None:
    """The recreation rule must not disturb the other buckets."""
    cases = {
        # markets / drop-in -> things to do
        "Lake Havasu Farmers Market": (None, True, time(8, 0), None, "things_to_do"),
        # physical sports / fitness
        "Sunrise Yoga Flow": (None, True, time(7, 0), None, "fitness"),
        "Adult Wrestling": (None, True, time(18, 0), None, "fitness"),
        "Pickleball Open Play": (None, False, time(0, 0), None, "fitness"),
        # non-physical instruction -> classes
        "Cooking Class": (None, False, time(17, 0), None, "classes"),
        "Watercolor Workshop": (None, True, time(13, 0), None, "classes"),
        # special / festival -> events
        "London Bridge Days Festival": (None, False, time(12, 0), None, "events"),
    }
    for title, (tags, rec, st, et, expected) in cases.items():
        assert _home_group(title, tags, False, rec, st, et) == expected, title


# --- Item 1: no dead rows --------------------------------------------------


def test_providerless_class_row_has_no_fake_self_link() -> None:
    """A provider-less class shows in the feed but carries NO link — we no longer
    fabricate a self-referential ``/events-ui?date=…#program-…`` anchor that just
    points back at this same bare row (no real source)."""
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_providerless_class(db, title="Pony / Lead Line Rides", days=["monday"]))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        ttd = _group(feed, "things_to_do")
        row = next(r for r in ttd["rows"] if "Pony" in r["title"] or "Lead Line" in r["title"])
        assert not row.get("url"), "providerless row must not fabricate a link"
        assert "#program" not in (row.get("url") or "")
    finally:
        _cleanup(eids, [])


def test_no_fake_self_anchor_rows_across_next_7_days() -> None:
    """No feed row over the next 7 days carries a fabricated self-referential
    anchor ('#' or '#program-…'). Real destinations and link-less rows are fine;
    a self-anchor back into the same page is not."""
    eids: list[str] = []
    mids: list[str] = []
    with SessionLocal() as db:
        # A provider-less class every day, a normal event, and a movie — so all
        # three row shapes are exercised.
        eids.append(_add_providerless_class(db, title="Pony / Lead Line Rides", days=_ALL_DAYS))
        eids.append(_add_event(db, title="ZZ Beach Cleanup", start=time(9, 0), loc="Beach"))
        mids.append(_add_movie(db, film="ZZ Some Film", sid=f"f-{uuid.uuid4().hex[:6]}",
                               theater_slug="star-cinemas", theater_name="Star Cinemas"))
        db.commit()
    try:
        for offset in range(7):
            day = _DAY + timedelta(days=offset)
            now = datetime(day.year, day.month, day.day, 6, 0, tzinfo=_LHC)
            with SessionLocal() as db:
                feed = today_feed(db, day=day, now=now)
            for row in _all_rows(feed):
                url = row.get("url") or ""
                assert url != "#", f"href='#' on {day}: {row.get('title')!r}"
                assert "#program" not in url, f"fake self-anchor on {day}: {row.get('title')!r}"
    finally:
        _cleanup(eids, mids)


# --- Item 2: case/space-insensitive movie de-dup (home feed) ----------------


def test_home_feed_merges_case_variant_film_across_theaters() -> None:
    """"The Death of Robin Hood" (Star) and "The Death Of Robin Hood" (Movies
    Havasu) collapse to ONE film row; the distinct-film count is 1."""
    s = uuid.uuid4().hex[:6]
    mids: list[str] = []
    with SessionLocal() as db:
        mids.append(_add_movie(db, film=f"The Death of Robin Hood {s}", sid=f"sc-{s}",
                               theater_slug="star-cinemas", theater_name="Star Cinemas", at=time(12, 40)))
        mids.append(_add_movie(db, film=f"The Death Of Robin Hood {s}", sid=f"mh-{s}",
                               theater_slug="movies-havasu", theater_name="Movies Havasu", at=time(13, 0)))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        movies = _group(feed, "movies")
        cards = [f for f in movies["films"] if "robin hood" in f["title"].casefold()]
        assert len(cards) == 1, [c["title"] for c in cards]
        assert len(cards[0]["theaters"]) == 2  # both theaters merged into one card
        assert feed["counts"]["movies"] == 1
    finally:
        _cleanup([], mids)
