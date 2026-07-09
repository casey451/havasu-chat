"""movie_showtimes store: upsert idempotency, prune, free-kids query, and the
kids-series loader records."""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import MovieShowtime
from app.movies.queries import has_free_kids, movies_today
from app.movies.store import (
    ShowtimeRecord,
    cross_check_autocorrected,
    prune_past,
    upsert_showtimes,
)

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
            assert c1 == {"created": 2, "updated": 0, "quarantined": 0, "auto_corrected": 0}
            # Re-run with the same stable ids -> updates, no new rows.
            c2 = upsert_showtimes(db, [_rec("s1", day=day, hh=12), _rec("s2", day=day, hh=14)])
            assert c2 == {"created": 0, "updated": 2, "quarantined": 0, "auto_corrected": 0}
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
            assert counts == {"created": 1, "updated": 0, "quarantined": 1, "auto_corrected": 0}
            times = {
                r.source_stable_id: r.show_time
                for r in db.scalars(select(MovieShowtime).where(MovieShowtime.source == SRC)).all()
            }
            assert times == {"moana-pm": time(16, 0)}  # only the plausible row landed
    finally:
        _cleanup()


def test_upsert_autocorrects_movies_havasu_flip():
    """Movies Havasu is an AUTO_CORRECT source (its backend flips PM matinees to
    AM): a <9 AM Moana is corrected +12h, tagged ``auto_corrected``, and STORED
    (so the real matinee shows) — not quarantined."""
    day = date(2099, 8, 7)
    rec = ShowtimeRecord(
        source="movies_havasu", source_stable_id="mh-moana-flip",
        theater_slug="movies-havasu", theater_name="Movies Havasu",
        film_title="Moana", show_date=day, show_time=time(4, 0), booking_url="http://book",
    )
    try:
        with SessionLocal() as db:
            counts = upsert_showtimes(db, [rec])
            assert counts == {"created": 1, "updated": 0, "quarantined": 0, "auto_corrected": 1}
            row = db.scalars(
                select(MovieShowtime).where(
                    MovieShowtime.source == "movies_havasu",
                    MovieShowtime.source_stable_id == "mh-moana-flip",
                )
            ).one()
            assert row.show_time == time(16, 0)  # 04:00 flipped +12h
            assert "auto_corrected" in row.tags
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(MovieShowtime).where(MovieShowtime.source_stable_id == "mh-moana-flip")
            )
            db.commit()


def test_autocorrect_target_guards():
    """The two guards on the +12h flip (Casey 2026-07-08)."""
    from app.movies.store import _autocorrect_target

    assert _autocorrect_target(time(4, 0)) == time(16, 0)    # normal flip → 4 PM
    assert _autocorrect_target(time(8, 30)) == time(20, 30)  # in operating window
    # Guard 1 — never flip the midnight hour (a legit premiere).
    assert _autocorrect_target(time(0, 0)) is None
    assert _autocorrect_target(time(0, 45)) is None
    # Guard 2 — result must land inside the ~10 AM–10 PM operating window.
    assert _autocorrect_target(time(10, 30)) is None  # +12h = 10:30 PM, past close
    assert _autocorrect_target(time(11, 0)) is None   # +12h = 11 PM, past close


def test_autoflip_quarantines_midnight_hour():
    """A 12:xx AM Movies Havasu show (a real midnight premiere) is quarantined for
    review, NOT flipped to noon."""
    day = date(2099, 8, 8)
    rec = ShowtimeRecord(
        source="movies_havasu", source_stable_id="mh-midnight",
        theater_slug="movies-havasu", theater_name="Movies Havasu",
        film_title="Midnight Premiere", show_date=day, show_time=time(0, 30), booking_url="x",
    )
    try:
        with SessionLocal() as db:
            counts = upsert_showtimes(db, [rec])
            assert counts == {"created": 0, "updated": 0, "quarantined": 1, "auto_corrected": 0}
            gone = db.scalars(
                select(MovieShowtime).where(MovieShowtime.source_stable_id == "mh-midnight")
            ).first()
            assert gone is None  # quarantined — never written
    finally:
        with SessionLocal() as db:
            db.execute(delete(MovieShowtime).where(MovieShowtime.source_stable_id == "mh-midnight"))
            db.commit()


def test_cross_check_flags_wildly_off_correction():
    """The free Star Cinemas cross-check: an auto-corrected time consistent with
    Star Cinemas' window passes; one wildly outside it is flagged."""
    day = date(2099, 8, 9)
    film = "CrossCheck Film ZZ"
    ids = ["cc-mh", "cc-sc1", "cc-sc2"]

    def _seed(mh_time: time) -> None:
        with SessionLocal() as db:
            db.execute(delete(MovieShowtime).where(MovieShowtime.source_stable_id.in_(ids)))
            db.add_all([
                MovieShowtime(source="movies_havasu", source_stable_id="cc-mh",
                    theater_slug="movies-havasu", theater_name="Movies Havasu",
                    film_title=film, show_date=day, show_time=mh_time, tags=["auto_corrected"]),
                MovieShowtime(source="star_cinemas", source_stable_id="cc-sc1",
                    theater_slug="star-cinemas", theater_name="Star Cinemas",
                    film_title=film, show_date=day, show_time=time(14, 0), tags=[]),
                MovieShowtime(source="star_cinemas", source_stable_id="cc-sc2",
                    theater_slug="star-cinemas", theater_name="Star Cinemas",
                    film_title=film, show_date=day, show_time=time(18, 0), tags=[]),
            ])
            db.commit()

    try:
        # 4 PM is inside Star Cinemas' 2–6 PM window → no flag.
        _seed(time(16, 0))
        with SessionLocal() as db:
            assert not any(film in f for f in cross_check_autocorrected(db))
        # 9:30 PM is >3h past Star Cinemas' latest (6 PM) → flagged.
        _seed(time(21, 30))
        with SessionLocal() as db:
            assert any(film in f for f in cross_check_autocorrected(db))
    finally:
        with SessionLocal() as db:
            db.execute(delete(MovieShowtime).where(MovieShowtime.source_stable_id.in_(ids)))
            db.commit()


def test_upsert_keeps_free_kids_series_before_9am():
    """The kids series is whitelisted — an is_free showing before 9 AM is never
    quarantined (8 AM here to genuinely exercise the exemption)."""
    day = date(2099, 8, 6)
    try:
        with SessionLocal() as db:
            counts = upsert_showtimes(
                db, [_rec("kids", day=day, hh=8, free=True, title="Kids Summer Series")]
            )
            assert counts == {"created": 1, "updated": 0, "quarantined": 0, "auto_corrected": 0}
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
