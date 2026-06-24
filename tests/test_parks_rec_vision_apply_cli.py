"""The vision-scraper CLIs ingest via the shared event funnel on --apply.

Asserts the wiring (records -> ingest_event_records, dry_run=False, lands as
pending because these sources aren't auto-approve) without any live HTTP/LLM:
the pull functions and the ingest call are monkeypatched.
"""

from __future__ import annotations

from datetime import date, time

import app.contrib.event_ingest as ei
import scripts.parks_rec_calendar_pull as pcli
import scripts.senior_flyers_pull as scli
from app.contrib.event_ingest import IngestCounts
from app.contrib.event_record import EventRecord
from app.contrib.lhc_parks_rec_calendar import CalendarPullResult
from app.contrib.senior_center_vision import SeniorFlyerPullResult


def _rec(source: str) -> EventRecord:
    return EventRecord(
        source=source,
        title="Tiny Tots Move & Groove",
        start_date=date(2026, 7, 8),
        start_time=time(10, 0),
        url="https://www.lhcaz.gov/185/Parks-Recreation#cal|2026-07-08|tiny-tots|10-00",
        description="Drop-in. Source: LHC Parks & Rec monthly calendar.",
    )


def _capture_ingest(monkeypatch) -> dict:
    captured: dict = {}

    def fake_ingest(records, *, source, dry_run, **kw):
        captured["records"] = list(records)
        captured["source"] = source
        captured["dry_run"] = dry_run
        return IngestCounts(fetched=len(captured["records"]), inserted_pending=len(captured["records"]))

    monkeypatch.setattr(ei, "ingest_event_records", fake_ingest)
    return captured


def test_calendar_apply_ingests_records(monkeypatch) -> None:
    rec = _rec("parks_rec_calendar")
    monkeypatch.setattr(pcli, "pull_calendars", lambda **kw: CalendarPullResult(records=[rec]))
    captured = _capture_ingest(monkeypatch)

    rc = pcli.main(["--apply"])

    assert rc == 0
    assert captured["dry_run"] is False
    assert captured["source"] == "parks_rec_calendar"
    assert captured["records"] == [rec]


def test_flyers_apply_uses_flyer_source(monkeypatch) -> None:
    rec = _rec("parks_rec_flyers")
    monkeypatch.setattr(pcli, "pull_flyers", lambda **kw: CalendarPullResult(records=[rec]))
    captured = _capture_ingest(monkeypatch)

    rc = pcli.main(["--source", "flyers", "--apply"])

    assert rc == 0
    assert captured["source"] == "parks_rec_flyers"
    assert captured["dry_run"] is False


def test_senior_apply_ingests_records(monkeypatch) -> None:
    rec = _rec("senior_center_flyers")
    monkeypatch.setattr(scli, "pull_senior_flyers", lambda **kw: SeniorFlyerPullResult(records=[rec]))
    captured = _capture_ingest(monkeypatch)

    rc = scli.main(["--apply"])

    assert rc == 0
    assert captured["source"] == "senior_center_flyers"
    assert captured["dry_run"] is False
    assert captured["records"] == [rec]


def test_dry_run_default_does_not_ingest(monkeypatch) -> None:
    rec = _rec("parks_rec_calendar")
    monkeypatch.setattr(pcli, "pull_calendars", lambda **kw: CalendarPullResult(records=[rec]))
    # Avoid touching the DB classifier in this hermetic test.
    monkeypatch.setattr(pcli, "_classify_against_db", lambda records: None)
    called = {"ingest": False}
    monkeypatch.setattr(ei, "ingest_event_records", lambda *a, **k: called.__setitem__("ingest", True))

    rc = pcli.main([])

    assert rc == 0
    assert called["ingest"] is False
