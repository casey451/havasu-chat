"""Movie showtime grouping (app.movies.queries.group_showtimes) and the
general-events-feed exclusion of movie rows (app.home.sandstone)."""

from __future__ import annotations

import uuid
from datetime import date, time
from types import SimpleNamespace

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import sandstone
from app.movies.queries import _meta_line, group_showtimes

DAY = date(2026, 6, 19)


def ev(title, slug, hour, minute=0, *, loc, meta="PG · Drama · 2h", url="http://book", img="http://p.jpg"):
    return SimpleNamespace(
        title=title,
        date=DAY,
        tags=["movie", "showtime", slug],
        location_name=loc,
        description=f"{meta}\n\nSynopsis here.",
        image_url=img,
        event_url=url,
        start_time=None if hour is None else time(hour, minute),
        end_time=None,
    )


def test_meta_line_parses_meta_but_not_prose():
    assert _meta_line("PG · Adventure · 1h 42m\n\nThe toys are back.") == "PG · Adventure · 1h 42m"
    assert _meta_line("Just a long synopsis with no separator line at all.") == ""
    assert _meta_line(None) == ""


def test_groups_by_theater_then_film_sorted():
    events = [
        ev("Toy Story 5", "star-cinemas", 14, loc="Star Cinemas"),
        ev("Toy Story 5", "star-cinemas", 11, loc="Star Cinemas"),
        ev("Obsession", "movies-havasu", 19, loc="Movies Havasu"),
        ev("Toy Story 5", "movies-havasu", 13, loc="Movies Havasu"),
    ]
    groups = group_showtimes(events, day=DAY)
    # Known theaters in THEATER_ORDER: star-cinemas before movies-havasu.
    assert [g.slug for g in groups] == ["star-cinemas", "movies-havasu"]

    star = groups[0]
    assert star.name == "Star Cinemas"
    assert len(star.films) == 1
    toy = star.films[0]
    assert toy.title == "Toy Story 5"
    assert [s.label for s in toy.showtimes] == ["11 AM", "2 PM"]  # chronological
    assert toy.poster == "http://p.jpg"
    assert toy.rating == "PG"
    assert toy.meta == "Drama · 2h"


def test_drops_films_with_no_displayable_time():
    events = [
        ev("Toy Story 5", "star-cinemas", 11, loc="Star Cinemas"),
        ev("Mystery Film", "star-cinemas", None, loc="Star Cinemas"),  # no start time
    ]
    groups = group_showtimes(events, day=DAY)
    titles = [f.title for f in groups[0].films]
    assert titles == ["Toy Story 5"]


def test_ignores_non_movie_and_other_days():
    other = SimpleNamespace(
        title="Farmers Market", date=DAY, tags=["events"], location_name="Main St",
        description="", image_url=None, event_url="", start_time=time(9, 0), end_time=None,
    )
    wrong_day = ev("Toy Story 5", "star-cinemas", 11, loc="Star Cinemas")
    wrong_day.date = date(2026, 6, 20)
    groups = group_showtimes([other, wrong_day], day=DAY)
    assert groups == []


def test_films_sorted_by_earliest_showtime():
    events = [
        ev("Late Film", "star-cinemas", 21, loc="Star Cinemas"),
        ev("Early Film", "star-cinemas", 10, loc="Star Cinemas"),
    ]
    groups = group_showtimes(events, day=DAY)
    assert [f.title for f in groups[0].films] == ["Early Film", "Late Film"]


# --- general feed excludes movie rows ---------------------------------------


def _seed_event(db, *, title: str, on: date, tags: list[str]) -> str:
    ev_row = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=time(19, 0),
        location_name="Star Cinemas",
        location_normalized="star cinemas",
        description="",
        event_url="https://example.com/e",
        tags=tags,
        status="live",
        source="test_movies",
        verified=True,
    )
    db.add(ev_row)
    db.flush()
    eid = ev_row.entity_id
    db.commit()
    return eid


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def test_general_feed_excludes_movie_rows_keeps_regular_events():
    """Movie showtimes (tag ``movie``) are kept out of the general events feed
    loader so ~200/day showtimes never flood /events-ui or the home module;
    a same-day non-movie event still comes through."""
    day = date(2099, 7, 14)
    suffix = uuid.uuid4().hex[:6]
    movie_title = f"ZZ Movie Showtime {suffix}"
    fair_title = f"ZZ Street Fair {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_seed_event(db, title=movie_title, on=day, tags=["movie", "showtime", "star-cinemas"]))
        eids.append(_seed_event(db, title=fair_title, on=day, tags=["events"]))
    try:
        with SessionLocal() as db:
            by_day = sandstone._live_events_by_day(db, window_start=day, window_end=day)
        titles = {ev_row.title for ev_row in by_day.get(day, [])}
        assert movie_title not in titles  # filtered out of the general feed
        assert fair_title in titles  # regular events unaffected
    finally:
        _cleanup(eids)
