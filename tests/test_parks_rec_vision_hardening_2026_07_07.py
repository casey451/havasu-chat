"""P&R vision hardening (2026-07-07): the flyer→event parse must QUARANTINE a
row it cannot trust rather than publish a wrong one — "a daily planner that's
wrong is worse than one that's incomplete."

Golden bug (live on prod): "Glow in the Dark Painting" rendered Tue Jul 7, 5:30
AM at venue "Jane Camlin". Reality: Wed Jul 8, 5:30 PM; Jane Camlin is the
instructor. Three compounding defects — meridiem-less time defaulting to AM, a
grid-cell-to-date off-by-one, and instructor text in the venue field.

These tests pin each guard and the end-to-end quarantine of the golden row.
"""

from __future__ import annotations

from datetime import date

from app.contrib import lhc_parks_rec_calendar as prc
from app.contrib import vision_calendar as vc

# The raw row the vision model emits from the July grid cell: the date is the
# off-by-one (2026-07-07 is a Tuesday), the weekday column was read correctly
# (Wednesday), the time has no printed AM/PM, and the instructor landed in
# ``location``.
GLOW_RAW: dict = {
    "title": "Glow in the Dark Painting",
    "date": "2026-07-07",
    "weekday": "Wednesday",
    "start_time": "5:30",
    "end_time": None,
    "location": "Jane Camlin",
    "cost": "$5 per person",
    "audience": "All Ages",
    "notes": None,
    "confidence": 0.9,
    "source_cell": "Glow in the Dark Painting  5:30  $5 per person  Jane Camlin  All Ages",
}


def _ref() -> "prc.GalleryImage":
    return prc.GalleryImage(
        url="https://www.lhcaz.gov/ImageRepository/Document?documentID=999",
        title="July-2026-Calendar",
        document_id="999",
        is_calendar=True,
        month=7,
        year=2026,
    )


# --------------------------------------------------------------------------- #
# Golden: the whole row is quarantined; no wrong field ever reaches the catalog
# --------------------------------------------------------------------------- #
def test_glow_golden_row_is_quarantined_end_to_end() -> None:
    rows, stats = vc.validate_rows([dict(GLOW_RAW)], month=7, year=2026)
    assert len(rows) == 1
    row = rows[0]

    # Held — never auto-published.
    assert row.should_hide is True
    # Meridiem-less "5:30" is NOT guessed to AM: the clock value is nulled and the
    # verbatim cell text is preserved for the reviewer.
    assert row.start_time is None
    assert "5:30" in row.source_cell
    assert stats.held_ambiguous_time == 1

    # Through the P&R adapter: the instructor is never the venue.
    rec = prc.row_to_event_record(row, _ref(), source=prc.SOURCE, kind="calendar")
    assert rec.venue_name == prc.DEFAULT_VENUE
    assert rec.venue_name != "Jane Camlin"
    assert rec.raw["should_hide"] is True


# --------------------------------------------------------------------------- #
# Guard 1 — ambiguous meridiem is held; explicit meridiem / 24h is kept
# --------------------------------------------------------------------------- #
def test_meridiem_ambiguous_detection() -> None:
    assert vc._meridiem_ambiguous("5:30") is True
    assert vc._meridiem_ambiguous("11:00") is True
    assert vc._meridiem_ambiguous("5:30 PM") is False
    assert vc._meridiem_ambiguous("5:30am") is False
    assert vc._meridiem_ambiguous("17:30") is False  # unambiguous 24h
    assert vc._meridiem_ambiguous("12:00") is False  # noon/midnight unambiguous
    assert vc._meridiem_ambiguous(None) is False


def test_meridiem_present_time_is_kept() -> None:
    raw = {
        "title": "Adult Acrylics",
        "date": "2026-07-09",
        "start_time": "5:30 PM",
        "location": "Community Center",
        "confidence": 0.95,
        "source_cell": "9 Adult Acrylics 5:30pm Community Center",
    }
    rows, stats = vc.validate_rows([raw], month=7, year=2026)
    assert rows[0].should_hide is False
    assert rows[0].start_time is not None
    assert rows[0].start_time.hour == 17
    assert stats.held_ambiguous_time == 0


# --------------------------------------------------------------------------- #
# Guard 2 — weekday/date invariant holds the WHOLE month on any mismatch
# --------------------------------------------------------------------------- #
def _clean(date_str: str, weekday: str) -> dict:
    return {
        "title": f"Class {date_str}",
        "date": date_str,
        "weekday": weekday,
        "start_time": "2:00 PM",
        "location": "Sara Park",
        "confidence": 0.95,
        "source_cell": f"{date_str} class",
    }


def test_aligned_weekdays_are_not_held() -> None:
    # 2026-07-08 is a Wednesday; 2026-07-09 a Thursday.
    rows, stats = vc.validate_rows(
        [_clean("2026-07-08", "Wednesday"), _clean("2026-07-09", "Thursday")],
        month=7,
        year=2026,
    )
    assert [r.should_hide for r in rows] == [False, False]
    assert stats.held_weekday_misalign == 0


def test_one_weekday_mismatch_holds_the_whole_month() -> None:
    # Second row's date (Thu) contradicts its printed "Wednesday" — a one-column
    # shift moves every event, so the entire batch is held.
    rows, stats = vc.validate_rows(
        [_clean("2026-07-08", "Wednesday"), _clean("2026-07-09", "Wednesday")],
        month=7,
        year=2026,
    )
    assert all(r.should_hide for r in rows)
    assert stats.held_weekday_misalign == 2


# --------------------------------------------------------------------------- #
# Guard 3 — venue must be a known facility, never a person / room
# --------------------------------------------------------------------------- #
def test_venue_classifier_accepts_real_locations() -> None:
    # Named facilities, generic venue words, and room codes are all real places —
    # including the sub-venues an earlier draft wrongly rejected (Kitchen, Site 6).
    for good in (
        "Aquatic Center",
        "Sara Park Ballfields",
        "aquatic",  # fragment of "Aquatic Center"
        "Lake Havasu City Parks & Recreation",
        "Community Center",
        "Wheeler Park",
        "Kitchen",
        "Site 6",  # = Site Six, spelled with a numeral
        "S3 - Room 153/154",
    ):
        assert prc.is_known_facility(good) is True, good


def test_venue_classifier_strict_accepts_only_named_facilities() -> None:
    # strict=True (the WS6.3 review lint): a NAMED facility (or the default venue)
    # passes; a bare generic word / room code / person name does NOT — it's
    # ambiguous and worth a human glance.
    for named in (
        "Aquatic Center", "Community Center", "Wheeler Park",
        "aquatic", "Lake Havasu City Parks & Recreation",
    ):
        assert prc.is_known_facility(named, strict=True) is True, named
    for ambiguous in ("Kitchen", "Site 6", "S3 - Room 153/154", "Room 12", "Jane Camlin"):
        assert prc.is_known_facility(ambiguous, strict=True) is False, ambiguous


def test_venue_classifier_rejects_person_names() -> None:
    # A mis-mapped instructor names no place. "S3 - Jane Camlin" has a building
    # tag but no room word, so it stays a reject (the real "S3 - Room 153" passes
    # above). Even a known instructor first-name is rejected by absence of a place.
    for bad in ("Jane Camlin", "S3 - Jane Camlin", "Margie Smith", None, ""):
        assert prc.is_known_facility(bad) is False, bad


def test_instructor_in_venue_is_rejected_and_held() -> None:
    row = vc.VisionEventRow(
        title="Kids Clay Series",
        event_date=date(2026, 7, 16),
        start_time=None,
        end_time=None,
        location="Jane Camlin",
        cost="$5",
        audience="Kids",
        notes=None,
        confidence=0.95,
        source_cell="16 Kids Clay Series Jane Camlin",
        should_hide=False,
    )
    rec = prc.row_to_event_record(row, _ref(), source=prc.SOURCE, kind="calendar")
    assert rec.venue_name == prc.DEFAULT_VENUE
    assert rec.raw["should_hide"] is True


def test_known_facility_venue_is_preserved_and_not_held() -> None:
    row = vc.VisionEventRow(
        title="Lap Swim",
        event_date=date(2026, 7, 16),
        start_time=None,
        end_time=None,
        location="Aquatic Center",
        cost=None,
        audience=None,
        notes=None,
        confidence=0.95,
        source_cell="16 Lap Swim Aquatic Center",
        should_hide=False,
    )
    rec = prc.row_to_event_record(row, _ref(), source=prc.SOURCE, kind="calendar")
    assert rec.venue_name == "Aquatic Center"
    assert rec.raw["should_hide"] is False
