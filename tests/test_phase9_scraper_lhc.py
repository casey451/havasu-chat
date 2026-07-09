"""Phase 9b — LHC library (Trumba) + parks-rec (CivicPlus) scrapers."""

from __future__ import annotations

from datetime import date, timedelta

from app.events.scrapers.ical_parse import parse_ical_events
from app.events.scrapers.lhc_library import LhcLibraryClient
from app.events.scrapers.lhc_parks_rec import LhcParksRecClient

# Use a date safely in the future so discover()'s "drop past events" filter
# (ev.start.date() < today) keeps the sample. Previously hard-coded to
# 2026-06-15, which silently broke both discover tests once that date passed.
_FUTURE = date.today() + timedelta(days=14)
_DSTAMP = _FUTURE.strftime("%Y%m%d")

SAMPLE_ICAL = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Library Story Time
UID:http://uid.trumba.com/event/123
DTSTART;TZID=America/Phoenix:{_DSTAMP}T100000
DTEND;TZID=America/Phoenix:{_DSTAMP}T110000
LOCATION:Storytime Room
DESCRIPTION:Kids story hour
END:VEVENT
END:VCALENDAR
"""


def test_ical_parse_vevent() -> None:
    events = parse_ical_events(SAMPLE_ICAL)
    assert len(events) == 1
    assert events[0].summary == "Library Story Time"
    assert events[0].start.date().isoformat() == _FUTURE.isoformat()


def test_lhc_library_discover(monkeypatch) -> None:
    client = LhcLibraryClient()
    monkeypatch.setattr(client, "fetch_text", lambda url, **kw: SAMPLE_ICAL)
    hits = client.discover({})
    assert hits
    payload = client.to_event_payload(client.enrich(hits[0]))
    assert "Library" in payload.name


def test_lhc_parks_rec_ical_discover(monkeypatch) -> None:
    client = LhcParksRecClient()
    monkeypatch.setattr(client, "fetch_text", lambda url, **kw: SAMPLE_ICAL)
    hits = client.discover({})
    assert hits
    payload = client.to_event_payload(client.enrich(hits[0]))
    assert payload.venue_name
