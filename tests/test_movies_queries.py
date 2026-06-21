"""Movie showtime grouping (movie_showtimes table) + the defensive events-feed
exclusion (movies must never appear in the general events feed)."""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event, MovieShowtime
from app.events.queries import events_in_window
from app.home import sandstone
from app.movies.queries import group_showtimes

DAY = date(2099, 6, 22)


def ms(
    title: str,
    slug: str,
    hh: int,
    mm: int = 0,
    *,
    name: str,
    rating: str = "PG",
    genre: str = "Drama",
    runtime: int = 120,
    poster: str = "http://p.jpg",
    url: str = "http://book",
    on: date | None = None,
) -> MovieShowtime:
    return MovieShowtime(
        source="test",
        source_stable_id=f"{title}-{hh}{mm}-{slug}",
        theater_slug=slug,
        theater_name=name,
        film_title=title,
        show_date=on or DAY,
        show_time=time(hh, mm),
        rating=rating,
        genre=genre,
        runtime_minutes=runtime,
        poster_url=poster,
        booking_url=url,
    )


def test_group_by_theater_then_film_sorted():
    rows = [
        ms("Toy Story 5", "star-cinemas", 14, name="Star Cinemas"),
        ms("Toy Story 5", "star-cinemas", 11, name="Star Cinemas"),
        ms("Obsession", "movies-havasu", 19, name="Movies Havasu"),
    ]
    groups = group_showtimes(rows, day=DAY)
    # Known theaters: star-cinemas before movies-havasu.
    assert [g.slug for g in groups] == ["star-cinemas", "movies-havasu"]
    star = groups[0]
    assert star.name == "Star Cinemas"
    assert len(star.films) == 1
    toy = star.films[0]
    assert toy.title == "Toy Story 5"
    assert [s.label for s in toy.showtimes] == ["11 AM", "2 PM"]  # chronological
    assert toy.rating == "PG"
    assert toy.meta == "Drama · 2h"
    assert toy.poster == "http://p.jpg"


def test_films_sorted_by_earliest_and_other_days_ignored():
    rows = [
        ms("Late Film", "star-cinemas", 21, name="Star Cinemas"),
        ms("Early Film", "star-cinemas", 10, name="Star Cinemas"),
        ms("Other Day", "star-cinemas", 9, name="Star Cinemas", on=date(2099, 6, 23)),
    ]
    groups = group_showtimes(rows, day=DAY)
    assert [f.title for f in groups[0].films] == ["Early Film", "Late Film"]


def test_meta_runtime_format():
    rows = [ms("Film", "star-cinemas", 12, name="Star Cinemas", genre="Comedy", runtime=102)]
    groups = group_showtimes(rows, day=DAY)
    assert groups[0].films[0].meta == "Comedy · 1h 42m"


def test_within_theater_dedup_is_case_and_space_insensitive():
    """One theater listing a film under case/spacing variants collapses to a
    single film card with all showtimes merged — not two near-duplicate cards."""
    rows = [
        ms("The Death of Robin Hood", "star-cinemas", 12, name="Star Cinemas"),
        ms("The Death Of Robin Hood", "star-cinemas", 15, name="Star Cinemas"),
        ms("Masters  of the Universe", "star-cinemas", 18, name="Star Cinemas"),
        ms("Masters Of The Universe", "star-cinemas", 20, name="Star Cinemas"),
    ]
    groups = group_showtimes(rows, day=DAY)
    films = groups[0].films
    assert len(films) == 2  # two distinct films, not four
    by_label = {f.title: [s.label for s in f.showtimes] for f in films}
    # Display keeps the first-seen spelling; showtimes from both variants merge.
    assert by_label["The Death of Robin Hood"] == ["12 PM", "3 PM"]
    assert by_label["Masters  of the Universe"] == ["6 PM", "8 PM"]


# --- general events feed still excludes any movie-tagged Event (defensive) -----


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
    day = date(2099, 7, 14)
    suffix = uuid.uuid4().hex[:6]
    movie_title = f"ZZ Movie Showtime {suffix}"
    fair_title = f"ZZ Street Fair {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_seed_event(db, title=movie_title, on=day, tags=["movie", "showtime"]))
        eids.append(_seed_event(db, title=fair_title, on=day, tags=["events"]))
    try:
        with SessionLocal() as db:
            by_day = sandstone._live_events_by_day(db, window_start=day, window_end=day)
        titles = {ev_row.title for ev_row in by_day.get(day, [])}
        assert movie_title not in titles
        assert fair_title in titles
    finally:
        _cleanup(eids)


def test_events_in_window_excludes_movie_rows():
    day = date(2099, 7, 15)
    suffix = uuid.uuid4().hex[:6]
    movie_title = f"ZZ Movie Windowed {suffix}"
    fair_title = f"ZZ Fair Windowed {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_seed_event(db, title=movie_title, on=day, tags=["movie", "showtime"]))
        eids.append(_seed_event(db, title=fair_title, on=day, tags=["events"]))
    try:
        with SessionLocal() as db:
            rows = events_in_window(db, window_start=day, window_end=day)
        titles = {ev_row.title for ev_row, _occ in rows}
        assert movie_title not in titles
        assert fair_title in titles
    finally:
        _cleanup(eids)
