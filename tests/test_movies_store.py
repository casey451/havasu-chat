"""movie_showtimes store: upsert idempotency, prune, free-kids query, and the
kids-series loader records."""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import MovieShowtime
from app.movies.queries import has_free_kids, movies_today
from app.movies.store import ShowtimeRecord, prune_past, upsert_showtimes

SRC = "test_store"


def _rec(sid: str, *, day: date, hh: int, free: bool = False, title: str = "Toy Story 5"):
    return ShowtimeRecord(
        source=SRC,
        source_stable_id=sid,
        theater_slug="star-cinemas",
        theater_name="Star Cinemas",
        film_title=title,
        show_date=day,
        show_time=time(hh, 0),
        rating="PG",
        genre="Adventure",
        runtime_minutes=102,
        poster_url="http://p.jpg",
        booking_url="http://book",
        is_free=free,
    )


def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(MovieShowtime).where(MovieShowtime.source == SRC))
        db.commit()


def test_upsert_is_idempotent_and_updates():
    day = date(2099, 8, 3)
    try:
        with SessionLocal() as db:
            c1 = upsert_showtimes(db, [_rec("s1", day=day, hh=11), _rec("s2", day=day, hh=14)])
            assert c1 == {"created": 2, "updated": 0}
            # Re-run with the same stable ids -> updates, no new rows.
            c2 = upsert_showtimes(db, [_rec("s1", day=day, hh=12), _rec("s2", day=day, hh=14)])
            assert c2 == {"created": 0, "updated": 2}
            rows = list(db.scalars(select(MovieShowtime).where(MovieShowtime.source == SRC)).all())
            assert len(rows) == 2
            s1 = next(r for r in rows if r.source_stable_id == "s1")
            assert s1.show_time == time(12, 0)  # field was updated
    finally:
        _cleanup()


def test_prune_past_removes_old_only():
    today = date(2099, 8, 10)
    try:
        with SessionLocal() as db:
            upsert_showtimes(
                db,
                [
                    _rec("old", day=today - timedelta(days=1), hh=11),
                    _rec("today", day=today, hh=12),
                    _rec("future", day=today + timedelta(days=2), hh=13),
                ],
            )
            removed = prune_past(db, before=today)
            assert removed == 1
            remaining = {
                r.source_stable_id
                for r in db.scalars(select(MovieShowtime).where(MovieShowtime.source == SRC)).all()
            }
            assert remaining == {"today", "future"}
    finally:
        _cleanup()


def test_has_free_kids_and_movies_today():
    day = date(2099, 8, 20)
    try:
        with SessionLocal() as db:
            upsert_showtimes(
                db,
                [
                    _rec("free1", day=day, hh=9, free=True, title="Smurfs"),
                    _rec("paid1", day=day, hh=19, free=False, title="Obsession"),
                ],
            )
        with SessionLocal() as db:
            assert has_free_kids(db, day=day) is True
            assert has_free_kids(db, day=day + timedelta(days=1)) is False
            titles = {m["title"] for m in movies_today(db, day=day, limit=6)}
            assert {"Smurfs", "Obsession"} <= titles
    finally:
        _cleanup()


def test_kids_loader_records_unique_and_free():
    from scripts.load_star_cinemas_kids_series import _records

    recs = _records()
    assert recs
    ids = [r.source_stable_id for r in recs]
    assert len(set(ids)) == len(ids)  # unique stable ids
    assert all(r.is_free for r in recs)
    assert all(r.film_title for r in recs)
