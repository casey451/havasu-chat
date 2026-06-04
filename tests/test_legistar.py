"""Legistar meeting parsing (source-expansion #3). No live HTTP — fixture JSON."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path

import pytest

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


def test_cli_apply_guarded() -> None:
    import scripts.legistar_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply"])
    assert exc.value.code == 2
