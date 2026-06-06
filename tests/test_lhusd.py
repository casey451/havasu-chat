"""LHUSD Thrillshare parsing (source-expansion #4). No live HTTP — fixtures."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from app.contrib import lhusd

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lhusd"


def test_parse_ical_filters_academic_span_noise() -> None:
    text = (FIXTURES / "calendar.ics").read_text(encoding="utf-8")
    events = lhusd.parse_ical(text)
    summaries = [e.summary for e in events]
    # The month-long "Summer School" all-day span is dropped; the timed board
    # meeting and the single-day in-service day are kept.
    assert "Summer School" not in summaries
    assert "Governing Board Regular Meeting" in summaries
    assert "Teacher In-Service Day (No School)" in summaries
    assert len(events) == 2


def test_all_day_detection() -> None:
    text = (FIXTURES / "calendar.ics").read_text(encoding="utf-8")
    events = {e.summary: e for e in lhusd.parse_ical(text)}
    assert events["Governing Board Regular Meeting"].all_day is False
    assert events["Teacher In-Service Day (No School)"].all_day is True


def test_parse_live_feeds_handles_field_variants() -> None:
    payload = json.loads((FIXTURES / "live_feeds.json").read_text(encoding="utf-8"))
    items = lhusd.parse_live_feeds(payload)
    # Third row (no title/url) is skipped.
    assert len(items) == 2
    assert items[0].title == "Kindergarten Registration Now Open"
    assert items[0].url.endswith("/9001")
    assert items[0].summary and "kindergartener" in items[0].summary.lower()
    # Second row uses headline/permalink/content variants.
    assert items[1].title == "District Wins STEM Grant"
    assert items[1].url.endswith("/9002")
    assert "robotics" in (items[1].summary or "")


def test_cli_dry_run_events(monkeypatch, capsys) -> None:
    import scripts.lhusd_pull as cli

    text = (FIXTURES / "calendar.ics").read_text(encoding="utf-8")
    monkeypatch.setattr(cli.lhusd, "fetch_events", lambda **_: lhusd.parse_ical(text))
    assert cli.main(["--feed", "events"]) == 0
    out = capsys.readouterr().out
    assert "lhusd:events — DRY RUN" in out
    assert "would-insert:   2" in out


# ----- EventRecord mapping (ingestion) -------------------------------------


def test_to_event_records_keeps_upcoming_and_unescapes_location() -> None:
    text = (FIXTURES / "calendar.ics").read_text(encoding="utf-8")
    events = lhusd.parse_ical(text)  # Governing Board 06-09 (timed), In-Service 08-14 (all-day)
    recs = lhusd.to_event_records(events, today=date(2026, 6, 5))
    by_title = {r.title: r for r in recs}
    assert "Governing Board Regular Meeting" in by_title
    assert "Teacher In-Service Day (No School)" in by_title
    board = by_title["Governing Board Regular Meeting"]
    assert board.source == "lhusd"
    assert board.start_date == date(2026, 6, 9)
    assert board.start_time is not None  # timed event keeps its time
    assert board.tags == ["school", "education", "lhusd"]
    in_service = by_title["Teacher In-Service Day (No School)"]
    assert in_service.start_time is None  # all-day -> no time


def test_to_event_records_drops_past() -> None:
    text = (FIXTURES / "calendar.ics").read_text(encoding="utf-8")
    events = lhusd.parse_ical(text)
    # After 08-14 everything in the fixture is past.
    assert lhusd.to_event_records(events, today=date(2026, 9, 1)) == []


def test_unescape_ical_text() -> None:
    assert (
        lhusd._unescape_ical_text("2675 Palo Verde Blvd S\\, Lake Havasu City\\, AZ")
        == "2675 Palo Verde Blvd S, Lake Havasu City, AZ"
    )


def test_cli_apply_ingests_upcoming(monkeypatch, capsys) -> None:
    """--apply maps upcoming calendar events to EventRecords and ingests."""
    import scripts.lhusd_pull as cli

    future = datetime(date.today().year + 1, 6, 9, 18, 0)
    ev = lhusd.LhusdEvent(
        summary="Governing Board Regular Meeting",
        start=future,
        end=None,
        location="2675 Palo Verde Blvd S\\, Lake Havasu City",
        all_day=False,
        url="https://example.com/board",
    )
    monkeypatch.setattr(cli.lhusd, "fetch_events", lambda **_: [ev])
    assert cli.main(["--apply"]) == 0
    out = capsys.readouterr().out
    assert "lhusd:events ingest complete" in out
    # lhusd is an official auto-approve source -> the upcoming event goes live.
    assert re.search(r"^\s*auto_approved\s+1\s*$", out, re.MULTILINE)


def test_cli_apply_news_does_not_ingest(monkeypatch, capsys) -> None:
    """The news feed has no surface yet: --apply must stay a dry-run, never ingest."""
    import scripts.lhusd_pull as cli

    payload = json.loads((FIXTURES / "live_feeds.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cli.lhusd, "fetch_live_feeds", lambda **_: lhusd.parse_live_feeds(payload))
    assert cli.main(["--feed", "news", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "lhusd:news — DRY RUN" in out
    assert "ingest complete" not in out
