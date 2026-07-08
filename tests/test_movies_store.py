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
            assert c1 == {"created": 2, "updated": 0, "quarantined": 0}
            # Re-run with the same stable ids -> updates, no new rows.
            c2 = upsert_showtimes(db, [_rec("s1", day=day, hh=12), _rec("s2", day=day, hh=14)])
            assert c2 == {"created": 0, "updated": 2, "quarantined": 0}
            rows = list(db.scalars(select(MovieShowtime).where(MovieShowtime.source == SRC)).all())
            assert len(rows) == 2
            s1 = next(r for r in rows if r.source_stable_id == "s1")
            assert s1.show_time == time(12, 0)  # field was updated
    finally:
        _cleanup()


def test_upsert_quarantines_pre_9am_showtime():
    """A before-9 AM showtime (AM/PM flip, e.g. a 4 PM Moana stored "4 AM") is
    quarantined — never written — while a legit afternoon show upserts normally."""
    day = date(2099, 8, 5)
    try:
        with SessionLocal() as db:
            counts = upsert_showtimes(
                db,
                [
                    _rec("moana-flip", day=day, hh=4, title="Moana 2"),  # 4 AM → quarantine
                    _rec("moana-pm", day=day, hh=16, title="Moana 2"),  # 4 PM → keep
                ],
            )
            assert counts == {"created": 1, "updated": 0, "quarantined": 1}
            times = {
                r.source_stable_id: r.show_time
                for r in db.scalars(select(MovieShowtime).where(MovieShowtime.source == SRC)).all()
            }
            assert times == {"moana-pm": time(16, 0)}  # only the plausible row landed
    finally:
        _cleanup()


def test_upsert_keeps_free_kids_series_before_9am():
    """The kids series is whitelisted — an is_free showing before 9 AM is never
    quarantined (8 AM here to genuinely exercise the exemption)."""
    day = date(2099, 8, 6)
    try:
        with SessionLocal() as db:
            counts = upsert_showtimes(
                db, [_rec("kids", day=day, hh=8, free=True, title="Kids Summer Series")]
            )
            assert counts == {"created": 1, "updated": 0, "quarantined": 0}
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


def test_movies_today_dedups_same_film_across_theaters():
    """§4e: a film playing at two theaters appears ONCE on the home strip
    (deduped by normalized title), keeping the earliest showtime's theater."""
    day = date(2099, 8, 21)
    recs = [
        ShowtimeRecord(
            source=SRC, source_stable_id="star-ts", theater_slug="star-cinemas",
            theater_name="Star Cinemas", film_title="Toy Story 5", show_date=day,
            show_time=time(13, 0), booking_url="http://star",
        ),
        ShowtimeRecord(
            source=SRC, source_stable_id="havasu-ts", theater_slug="movies-havasu",
            theater_name="Movies Havasu", film_title="Toy Story 5", show_date=day,
            show_time=time(11, 0), booking_url="http://havasu",
        ),
        _rec("obsession", day=day, hh=19, title="Obsession"),
    ]
    try:
        with SessionLocal() as db:
            upsert_showtimes(db, recs)
        with SessionLocal() as db:
            rows = movies_today(db, day=day, limit=6)
        titles = [r["title"] for r in rows]
        assert titles.count("Toy Story 5") == 1
        assert set(titles) == {"Toy Story 5", "Obsession"}
        ts = next(r for r in rows if r["title"] == "Toy Story 5")
        # Earliest showtime (11:00 at Movies Havasu) supplies the displayed row.
        assert ts["theater"] == "Movies Havasu"
        assert ts["url"] == "http://havasu"
    finally:
        _cleanup()


def test_star_cinemas_booking_url_falls_back_to_landing(monkeypatch):
    # A Veezi session with an empty web_session_url must still get a real booking
    # link — the theater's "Show Times" landing — never an empty url (which would
    # render as a dead href). A session that carries its own url keeps it.
    from app.movies import store

    fake_rows = [
        {
            "id": "100",
            "session_datetime": "2099-08-03T19:30:00+00:00",
            "status": "active",
            "web_session_url": "",  # blank — the free-show / missing case
            "film": {"title": "Supergirl"},
            "site": {"name": "Star Cinemas"},
        },
        {
            "id": "101",
            "session_datetime": "2099-08-03T21:00:00+00:00",
            "status": "active",
            "web_session_url": "https://ticketing.uswest.veezi.com/booking/?Id=abc",
            "film": {"title": "Supergirl"},
            "site": {"name": "Star Cinemas"},
        },
    ]
    monkeypatch.setattr(store, "_fetch_json", lambda url, **kw: fake_rows)
    recs = store.fetch_star_cinemas(today=date(2099, 8, 3))
    by_id = {r.source_stable_id: r for r in recs}
    assert by_id["100"].booking_url == store.STAR_CINEMAS_BOOKING_LANDING
    assert by_id["100"].booking_url  # never empty / None
    assert by_id["101"].booking_url == "https://ticketing.uswest.veezi.com/booking/?Id=abc"


def test_kids_loader_records_unique_and_free():
    from scripts.load_star_cinemas_kids_series import _records

    recs = _records()
    assert recs
    ids = [r.source_stable_id for r in recs]
    assert len(set(ids)) == len(ids)  # unique stable ids
    assert all(r.is_free for r in recs)
    assert all(r.film_title for r in recs)
