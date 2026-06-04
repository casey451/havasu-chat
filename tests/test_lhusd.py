"""LHUSD Thrillshare parsing (source-expansion #4). No live HTTP — fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_cli_apply_guarded() -> None:
    import scripts.lhusd_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply"])
    assert exc.value.code == 2
