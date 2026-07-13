"""America-250 re-date correction (2026-07-12 -> 2026-07-01) — gated + reversible."""

from __future__ import annotations

from datetime import time

import pytest

from app.db.database import SessionLocal
from app.db.models import Event
from scripts.fix_america250_redate_2026_07_12 import (
    EVENT_ID,
    EXPIRED,
    TRUE_DATE,
    WRONG_DATE,
    _apply_correction,
    _in_bad_state,
    _realign_url,
    _undo,
)

_TITLE = "Havasu Celebrates America 250 - Pizza Party, Open Swim, and Proclamation"
_BAD_URL = (
    "https://www.lhcaz.gov/185/Parks-Recreation"
    "#cal|2026-07-12|havasu-celebrates-america-250-pizza-party-open-swim-and-proclamation|12-00"
)
_GOOD_URL = _BAD_URL.replace("|2026-07-12|", "|2026-07-01|")


def _make_bad_row() -> Event:
    return Event(
        id=EVENT_ID,
        title=_TITLE,
        normalized_title=_TITLE.lower(),
        date=WRONG_DATE,
        start_time=time(12, 0),
        end_time=time(16, 0),
        location_name="Lake Havasu City Parks & Recreation",
        location_normalized="lake havasu city parks & recreation",
        description="For Pool. Cost: Free. Source: LHC Parks & Rec monthly calendar.",
        event_url=_BAD_URL,
        status="live",
        source="parks_rec_calendar",
    )


@pytest.fixture
def bad_row():
    with SessionLocal() as db:
        db.merge(_make_bad_row())
        db.commit()
    try:
        yield
    finally:
        with SessionLocal() as db:
            row = db.get(Event, EVENT_ID)
            if row is not None:
                db.delete(row)
                db.commit()


def test_realign_url_swaps_only_the_wrong_date_token() -> None:
    assert _realign_url(_BAD_URL) == _GOOD_URL
    # An already-correct or unrelated URL is untouched.
    assert _realign_url(_GOOD_URL) == _GOOD_URL
    assert _realign_url("") == ""
    assert _realign_url(None) is None


def test_in_bad_state_matches_only_the_target() -> None:
    ev = _make_bad_row()
    assert _in_bad_state(ev) is True
    ev.status = "expired"
    assert _in_bad_state(ev) is False
    ev.status = "live"
    ev.date = TRUE_DATE
    assert _in_bad_state(ev) is False


def test_dry_run_writes_nothing(bad_row) -> None:
    with SessionLocal() as db:
        n = _apply_correction(db, apply=False, undo_csv=None)
    assert n == 1
    with SessionLocal() as db:
        ev = db.get(Event, EVENT_ID)
        assert ev.date == WRONG_DATE
        assert ev.status == "live"
        assert ev.event_url == _BAD_URL


def test_apply_corrects_and_is_reversible(tmp_path, bad_row) -> None:
    undo = tmp_path / "undo.csv"
    with SessionLocal() as db:
        n = _apply_correction(db, apply=True, undo_csv=str(undo))
    assert n == 1
    with SessionLocal() as db:
        ev = db.get(Event, EVENT_ID)
        assert ev.date == TRUE_DATE
        assert ev.status == EXPIRED
        assert ev.event_url == _GOOD_URL
    assert undo.exists()

    # Guard: a second apply is a NO-OP (row no longer in the bad state).
    with SessionLocal() as db:
        assert _apply_correction(db, apply=True, undo_csv=None) == 0
        ev = db.get(Event, EVENT_ID)
        assert ev.date == TRUE_DATE and ev.status == EXPIRED

    # Undo restores the original date/status/url.
    with SessionLocal() as db:
        _undo(db, undo_from=str(undo), apply=True)
    with SessionLocal() as db:
        ev = db.get(Event, EVENT_ID)
        assert ev.date == WRONG_DATE
        assert ev.status == "live"
        assert ev.event_url == _BAD_URL


def test_missing_row_is_a_safe_noop() -> None:
    with SessionLocal() as db:
        # No row inserted (and clean up any stray, just in case).
        stray = db.get(Event, EVENT_ID)
        if stray is not None:
            db.delete(stray)
            db.commit()
        assert _apply_correction(db, apply=True, undo_csv=None) == 0
