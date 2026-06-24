"""Tests for the Parks & Rec vision calendar/flyer adapter.

Discovery, month/year parsing, row->EventRecord mapping, and the full
pull_calendars/pull_flyers orchestration are exercised with injected gallery
HTML + recorded model JSON (no live HTTP/LLM). The dedup regression uses the
real shared event funnel (SessionLocal) like the other DB-backed ingest tests.
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import date, time
from pathlib import Path

from app.contrib import lhc_parks_rec_calendar as prc
from app.contrib.vision_calendar import VisionEventRow

FIXTURES = Path(__file__).parent / "fixtures" / "parks_rec"
TODAY = date(2026, 6, 15)


def _gallery_html() -> str:
    return (FIXTURES / "gallery.html").read_text(encoding="utf-8")


def _calendar_json() -> str:
    return (FIXTURES / "calendar_model_output.json").read_text(encoding="utf-8")


def _flyer_json() -> str:
    return (FIXTURES / "flyer_model_output.json").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Month/year parsing
# --------------------------------------------------------------------------- #
def test_parse_month_year_with_explicit_year() -> None:
    assert prc.parse_month_year("July-2026-Calendar", today=TODAY) == (7, 2026)


def test_parse_month_year_infers_year() -> None:
    # June, today is June 15 2026 -> current year.
    assert prc.parse_month_year("June Calendar", today=TODAY) == (6, 2026)
    # January with today in June -> already passed this year -> next year.
    assert prc.parse_month_year("January Calendar", today=TODAY) == (1, 2027)


def test_infer_year_for_month() -> None:
    assert prc.infer_year_for_month(6, today=TODAY) == 2026
    assert prc.infer_year_for_month(7, today=TODAY) == 2026
    assert prc.infer_year_for_month(5, today=TODAY) == 2027


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def test_discover_calendar_images() -> None:
    refs = prc.discover_calendar_images(_gallery_html(), today=TODAY)
    titles = {r.title for r in refs}
    assert titles == {"July-2026-Calendar", "June Calendar"}
    july = next(r for r in refs if r.title.startswith("July"))
    assert july.month == 7 and july.year == 2026
    assert july.document_id == "12345"
    assert july.url == "https://www.lhcaz.gov/ImageRepository/Document?documentID=12345"


def test_discover_flyer_images_excludes_calendars_and_chrome() -> None:
    refs = prc.discover_flyer_images(_gallery_html(), today=TODAY)
    titles = {r.title for r in refs}
    assert "7-1-7-2-2026-Fouth-of-July-Baking" in titles
    assert "Little-Fish-1" in titles
    assert "City Logo" not in titles  # chrome/logo excluded
    assert "July-2026-Calendar" not in titles  # calendars excluded


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #
def _row(**kw) -> VisionEventRow:
    base = dict(
        title="Tiny Tots Move & Groove",
        event_date=date(2026, 7, 8),
        start_time=time(10, 0),
        end_time=time(10, 45),
        location="Aquatic Center",
        cost="$3",
        audience="toddlers",
        notes="Drop-in",
        confidence=0.95,
        source_cell="8 Tiny Tots 10:00a $3",
        should_hide=False,
    )
    base.update(kw)
    return VisionEventRow(**base)


def test_synthetic_url_format() -> None:
    url = prc.synthetic_url(_row())
    assert url.startswith("https://www.lhcaz.gov/185/Parks-Recreation#cal|2026-07-08|")
    assert url.endswith("|10-00")


def test_synthetic_url_no_time() -> None:
    assert prc.synthetic_url(_row(start_time=None)).endswith("|00-00")


def test_row_to_event_record_mapping() -> None:
    ref = prc.GalleryImage(
        url="https://www.lhcaz.gov/ImageRepository/Document?documentID=12345",
        title="July-2026-Calendar",
        document_id="12345",
        is_calendar=True,
        month=7,
        year=2026,
    )
    rec = prc.row_to_event_record(_row(), ref, source=prc.SOURCE, kind="calendar")
    assert rec.source == prc.SOURCE
    assert rec.title == "Tiny Tots Move & Groove"
    assert rec.start_date == date(2026, 7, 8)
    assert rec.start_time == time(10, 0)
    assert rec.venue_name == "Aquatic Center"
    assert rec.image_url == ref.url
    assert rec.url.startswith("https://www.lhcaz.gov/185/Parks-Recreation#cal|")
    assert "Cost: $3." in rec.description
    assert "Source: LHC Parks & Rec monthly calendar." in rec.description
    assert rec.raw["source_cell"] == "8 Tiny Tots 10:00a $3"
    assert rec.raw["kind"] == "calendar"
    assert rec.tags  # at least a content category


def test_row_to_event_record_defaults_venue() -> None:
    ref = prc.GalleryImage(
        url="u", title="t", document_id=None, is_calendar=True, month=7, year=2026
    )
    rec = prc.row_to_event_record(_row(location=None), ref, source=prc.SOURCE, kind="calendar")
    assert rec.venue_name == prc.DEFAULT_VENUE


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def test_pull_calendars_residue_and_guards() -> None:
    raw_by_url = {
        "https://www.lhcaz.gov/ImageRepository/Document?documentID=12345": _calendar_json(),
        "https://www.lhcaz.gov/ImageRepository/Document?documentID=12346": '{"events":[]}',
    }
    result = prc.pull_calendars(
        html=_gallery_html(),
        today=TODAY,
        write_snapshot=False,
        raw_text_by_url=raw_by_url,
    )
    titles = {r.title for r in result.records}
    assert titles == {"Tiny Tots Move & Groove", "Free Summer Craft Series"}
    assert result.dropped_out_of_month == 1  # August Pizza Party
    assert result.dropped_no_provenance == 1  # empty source_cell
    assert result.held_low_confidence == 1  # Free Summer Craft (0.6)
    assert all(r.source == prc.SOURCE for r in result.records)
    held = [r for r in result.records if r.raw.get("should_hide")]
    assert {r.title for r in held} == {"Free Summer Craft Series"}


def test_pull_flyers_maps_single_event() -> None:
    flyer_url = "https://www.lhcaz.gov/ImageRepository/Document?documentID=22222"
    result = prc.pull_flyers(
        html=_gallery_html(),
        today=TODAY,
        write_snapshot=False,
        max_flyers=1,
        raw_text_by_url={flyer_url: _flyer_json()},
    )
    assert len(result.records) == 1
    rec = result.records[0]
    assert rec.source == prc.FLYER_SOURCE
    assert rec.title == "Fourth of July Baking"
    assert rec.start_date == date(2026, 7, 1)
    assert "event flyer" in rec.description


def test_pull_flyers_drops_stray_out_of_flyer_date() -> None:
    # Two dates in one flyer where the second is a hallucinated different month:
    # each row self-bounds to its own parsed month, but a no-provenance stray is
    # still dropped.
    flyer_url = "https://www.lhcaz.gov/ImageRepository/Document?documentID=33333"
    payload = json.dumps(
        {
            "events": [
                {
                    "title": "Little Fish Swim",
                    "date": "2026-07-09",
                    "start_time": "08:30",
                    "source_cell": "Little Fish July 9 8:30am",
                    "confidence": 0.9,
                },
                {
                    "title": "Phantom",
                    "date": "2026-09-09",
                    "source_cell": "",
                    "confidence": 0.9,
                },
            ]
        }
    )
    result = prc.pull_flyers(
        html=_gallery_html(),
        today=TODAY,
        write_snapshot=False,
        max_flyers=8,
        raw_text_by_url={flyer_url: payload},
    )
    assert {r.title for r in result.records} == {"Little Fish Swim"}
    assert result.dropped_no_provenance == 1


# --------------------------------------------------------------------------- #
# Dedup regression — defer to a richer existing (WebTrac-equivalent) row
# --------------------------------------------------------------------------- #
def test_calendar_row_matching_existing_event_is_skipped() -> None:
    from app.contrib.event_ingest import ingest_event_records
    from app.contrib.event_record import EventRecord

    suf = _uuid.uuid4().hex[:8]
    title = f"Dodgeball USA {suf}"
    venue = prc.DEFAULT_VENUE
    d = date(2026, 12, 7)

    # Seed a live event via an auto-approve civic source (stands in for the
    # richer WebTrac registration row the calendar overlaps with).
    existing = EventRecord(
        source="legistar",
        title=title,
        start_date=d,
        start_time=time(18, 0),
        venue_name=venue,
        url=f"https://register.lhcaz.gov/webtrac/{suf}",
        description="Adult dodgeball league night at the rec center." * 2,
    )
    seed = ingest_event_records([existing], source="legistar", dry_run=False)
    assert seed.auto_approved + seed.inserted_pending == 1

    # The calendar scraper reads the same event off the monthly flyer image.
    ref = prc.GalleryImage(
        url="https://www.lhcaz.gov/ImageRepository/Document?documentID=12345",
        title="December-2026-Calendar",
        document_id="12345",
        is_calendar=True,
        month=12,
        year=2026,
    )
    cal_row = _row(
        title=title, event_date=d, start_time=time(18, 0), location=None, should_hide=False
    )
    cal_rec = prc.row_to_event_record(cal_row, ref, source=prc.SOURCE, kind="calendar")

    counts = ingest_event_records([cal_rec], source=prc.SOURCE, dry_run=True)
    # The calendar row must NOT add a second copy: it merges/skips against the
    # existing richer row.
    assert counts.auto_approved == 0
    assert (
        counts.skipped_duplicate_persisted
        + counts.merged_duplicate
        + counts.skipped_existing_pending
        >= 1
    )
