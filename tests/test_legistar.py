"""Legistar meeting parsing (source-expansion #3). No live HTTP — fixture JSON."""

from __future__ import annotations

import json
import re
from datetime import date, time
from pathlib import Path

from app.contrib import legistar

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "legistar"


def _events() -> list[dict]:
    return json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))


def test_parse_events_maps_meetings() -> None:
    meetings = legistar.parse_events(_events())
    # The body-less row is skipped.
    assert len(meetings) == 2
    council = meetings[0]
    assert council.body_name == "City Council"
    assert council.meeting_date is not None
    assert council.meeting_date.isoformat() == "2026-06-09"
    assert council.start_time == time(18, 0)
    assert council.agenda_url and "View.ashx" in council.agenda_url
    assert council.minutes_url is None  # empty string -> None
    assert council.start_datetime is not None
    assert council.start_datetime.hour == 18


def test_dedupe_key_uses_event_id() -> None:
    meetings = legistar.parse_events(_events())
    assert meetings[0].dedupe_key() == "legistar:4521"


def test_minutes_url_present_when_published() -> None:
    meetings = legistar.parse_events(_events())
    pz = meetings[1]
    assert pz.body_name == "Planning and Zoning Commission"
    assert pz.minutes_url and "M=M" in pz.minutes_url


def test_cli_dry_run(monkeypatch, capsys) -> None:
    import scripts.legistar_pull as cli

    meetings = legistar.parse_events(_events())
    monkeypatch.setattr(cli.legistar, "fetch_events", lambda **_: meetings)
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "legistar — DRY RUN" in out
    assert "would-insert:   2" in out


# ----- EventRecord mapping (ingestion) -------------------------------------


def test_to_event_records_keeps_upcoming_drops_past() -> None:
    meetings = legistar.parse_events(_events())  # City Council 06-09, P&Z 06-03
    recs = legistar.to_event_records(meetings, today=date(2026, 6, 5))
    # Only the 06-09 council meeting is on/after today; the 06-03 P&Z is dropped.
    assert len(recs) == 1
    rec = recs[0]
    assert rec.source == "legistar"
    assert rec.title == "City Council Meeting"  # body gets a "Meeting" suffix
    assert rec.start_date == date(2026, 6, 9)
    assert rec.start_time == time(18, 0)
    assert rec.tags == ["civic", "government", "meeting"]
    assert rec.description and len(rec.description) >= 20
    assert rec.url and "View.ashx" in rec.url  # agenda link preferred


def test_to_event_records_all_past_is_empty() -> None:
    meetings = legistar.parse_events(_events())
    assert legistar.to_event_records(meetings, today=date(2027, 1, 1)) == []


def test_cli_apply_ingests_upcoming(monkeypatch, capsys) -> None:
    """--apply maps upcoming meetings to EventRecords and ingests (auto-approve)."""
    import scripts.legistar_pull as cli

    future = date(date.today().year + 1, 6, 9)
    meeting = legistar.LegistarMeeting(
        event_id=9001,
        body_name="City Council",
        meeting_date=future,
        start_time=time(18, 0),
        location="Council Chambers",
        agenda_url="https://example.com/agenda",
        minutes_url=None,
    )
    monkeypatch.setattr(cli.legistar, "fetch_events", lambda **_: [meeting])
    assert cli.main(["--apply"]) == 0
    out = capsys.readouterr().out
    assert "legistar ingest complete" in out
    # legistar is a civic auto-approve source -> the upcoming meeting goes live.
    assert re.search(r"^\s*auto_approved\s+1\s*$", out, re.MULTILINE)


def test_cli_apply_exits_nonzero_on_ingest_errors(monkeypatch) -> None:
    """Record-level ingest failures must fail the cron run, not hide behind exit 0."""
    import app.contrib.event_ingest as ingest_mod
    import scripts.legistar_pull as cli

    meetings = legistar.parse_events(_events())
    monkeypatch.setattr(cli.legistar, "fetch_events", lambda **_: meetings)
    monkeypatch.setattr(
        ingest_mod, "ingest_event_records",
        lambda *a, **k: ingest_mod.IngestCounts(errors=2),
    )
    assert cli.main(["--apply"]) == 1
