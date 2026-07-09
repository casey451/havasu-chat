"""The Movies Havasu AM/PM-flip correction (scripts/fix_movies_havasu_ampm_flips).

Corrects only the lint-flagged <9 AM Movies Havasu rows (+12h), leaves legit
afternoon shows and whitelisted kids-series matinees alone, and is idempotent.
"""

from __future__ import annotations

import importlib
from datetime import date, time

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import MovieShowtime

fix = importlib.import_module("scripts.fix_movies_havasu_ampm_flips")

SRC = "movies_havasu"
DAY = date(2099, 7, 15)


def _row(sid: str, hh: int, *, title: str, free: bool = False, source: str = SRC) -> MovieShowtime:
    return MovieShowtime(
        source=source,
        source_stable_id=sid,
        theater_slug="movies-havasu",
        theater_name="Movies Havasu",
        film_title=title,
        show_date=DAY,
        show_time=time(hh, 0),
        is_free=free,
    )


def _cleanup(ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(MovieShowtime).where(MovieShowtime.id.in_(ids)))
        db.commit()


def test_shift_12h() -> None:
    assert fix._shift_12h(time(4, 0)) == time(16, 0)
    assert fix._shift_12h(time(8, 30)) == time(20, 30)


def test_corrects_only_flagged_rows() -> None:
    rows = [
        _row("flip", 4, title="Moana"),            # 4 AM flip → corrected to 16:00
        _row("legit", 16, title="Moana"),          # 4 PM already correct → untouched
        _row("kids", 8, title="Kids Series", free=True),  # free matinee whitelisted → untouched
        _row("other", 4, title="Elio", source="star_cinemas"),  # other source → untouched
    ]
    with SessionLocal() as db:
        db.add_all(rows)
        db.commit()
        ids = [r.id for r in rows]
    try:
        with SessionLocal() as db:
            # Dry run: reports the one candidate, writes nothing.
            assert fix._apply_correction(db, apply=False, undo_csv=None) == 1
        with SessionLocal() as db:
            times = {r.source_stable_id: r.show_time for r in db.scalars(
                select(MovieShowtime).where(MovieShowtime.id.in_(ids))).all()}
        assert times["flip"] == time(4, 0)  # dry run left it alone

        with SessionLocal() as db:
            assert fix._apply_correction(db, apply=True, undo_csv=None) == 1
        with SessionLocal() as db:
            times = {r.source_stable_id: r.show_time for r in db.scalars(
                select(MovieShowtime).where(MovieShowtime.id.in_(ids))).all()}
        assert times["flip"] == time(16, 0)   # corrected +12h
        assert times["legit"] == time(16, 0)  # untouched
        assert times["kids"] == time(8, 0)    # whitelisted, untouched
        assert times["other"] == time(4, 0)   # other source, untouched

        # Idempotent: a second run finds nothing to correct.
        with SessionLocal() as db:
            assert fix._apply_correction(db, apply=True, undo_csv=None) == 0
    finally:
        _cleanup(ids)
