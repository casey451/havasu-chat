"""Regression tests for the 2026-07-01 audit events/contrib/tz bug batch.

Covers: offset-aware timestamps converting to Phoenix wall-clock before going
naive, iCal TEXT unescaping + bad-VEVENT tolerance, the parks-rec RSS TBD
sentinel, the shared weekend-window semantics, the over-broad wait-time gap,
the day-agenda singular voice, /today water-temp attribution, and multi-zone
NWS alert fetching.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.chat.component_builders import fallback_day_agenda_voice
from app.chat.intent_classifier import IntentResult
from app.chat.unified_router import _catalog_gap_response
from app.contrib.event_record import parse_dt
from app.contrib.lhusd import _parse_dt as lhusd_parse_dt
from app.events.scrapers.ical_parse import parse_ical_events
from app.groups.themed_group_stream import _when_window

# --- tz-aware -> Phoenix wall-clock ------------------------------------------


def test_event_record_parse_dt_converts_utc_to_phoenix():
    # 19:00Z is NOON Phoenix (UTC-7, no DST) — stripping tzinfo without
    # converting stored it as 7 PM.
    dt = parse_dt("2026-07-04T19:00:00Z")
    assert dt == datetime(2026, 7, 4, 12, 0, 0)
    assert dt.tzinfo is None


def test_event_record_parse_dt_keeps_naive_as_local():
    assert parse_dt("2026-07-04T19:00:00") == datetime(2026, 7, 4, 19, 0, 0)


def test_event_record_parse_dt_handles_other_offsets():
    # 10:00 Eastern (UTC-4 in July) == 07:00 Phoenix.
    dt = parse_dt("2026-07-04T10:00:00-04:00")
    assert dt == datetime(2026, 7, 4, 7, 0, 0)


def test_lhusd_parse_dt_converts_z_suffix():
    assert lhusd_parse_dt("2026-07-04T19:00:00Z") == datetime(2026, 7, 4, 12, 0, 0)


# --- iCal TEXT unescaping + bad-VEVENT tolerance ------------------------------


_ICS_TEMPLATE = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:one
SUMMARY:Story Time\\, Kids
LOCATION:Library\\, Room A\\; East Wing
DTSTART:20990801T100000
END:VEVENT
BEGIN:VEVENT
UID:bad
SUMMARY:Garbled
DTSTART:not-a-date
END:VEVENT
BEGIN:VEVENT
UID:two
SUMMARY:Second Event
DTSTART:20990802T110000
END:VEVENT
END:VCALENDAR
"""


def test_ical_text_escapes_are_unescaped():
    events = parse_ical_events(_ICS_TEMPLATE)
    ev = next(e for e in events if e.uid == "one")
    assert ev.summary == "Story Time, Kids"
    assert ev.location == "Library, Room A; East Wing"


def test_ical_bad_dtstart_skips_event_not_feed():
    events = parse_ical_events(_ICS_TEMPLATE)
    uids = {e.uid for e in events}
    assert "bad" not in uids
    assert {"one", "two"} <= uids  # the rest of the feed survives


# --- parks-rec RSS: no fabricated 9 AM ----------------------------------------


def test_parks_rec_rss_missing_time_uses_tbd_sentinel():
    from app.contrib.ingest_base import RawHit
    from app.events.scrapers.lhc_parks_rec import LhcParksRecClient

    scraper = LhcParksRecClient()
    hit = RawHit(
        source=scraper.source_name,
        source_stable_id="https://example.com/e1",
        name="Kids Craft Day",
        raw={"rss": {"description": "<strong>Event date:</strong> Aug 3, 2099"}},
    )
    enriched = scraper.enrich(hit)
    # 00:00 is the is_time_tbd sentinel ("Time TBD"); 9 AM was fabricated.
    assert enriched.enriched["start_iso"].endswith("T00:00:00")


# --- weekend window shared semantics -------------------------------------------


def test_themed_group_weekend_window_includes_friday():
    # Wednesday 2026-07-01 -> this-weekend must start Friday 07-03 (the
    # event_window_for_chip contract), not Saturday (the old local copy).
    start, end = _when_window("this-weekend", date(2026, 7, 1))
    assert start == date(2026, 7, 3)
    assert end == date(2026, 7, 5)


def test_themed_group_unknown_when_is_none():
    assert _when_window("someday", date(2026, 7, 1)) is None
    assert _when_window(None, date(2026, 7, 1)) is None


# --- wait-time gap: shape-tightened ---------------------------------------------


def _ir(raw: str, sub: str = "GENERAL_QUESTION") -> IntentResult:
    return IntentResult(
        mode="ask", sub_intent=sub, confidence=0.9,
        entity=None, raw_query=raw, normalized_query=raw.lower(),
    )


def test_wait_time_gap_still_fires_on_wait_time_shapes():
    for q in ("what's the wait time at chico's", "how long is the wait there"):
        resp = _catalog_gap_response(_ir(q))
        assert resp is not None and "wait-time" in resp


def test_bare_wait_no_longer_hijacks_queries():
    # "can't wait" is anticipation, not a wait-time question.
    resp = _catalog_gap_response(
        _ir("I can't wait for the balloon festival — anything going on?")
    )
    assert resp is None or "wait-time" not in resp


# --- day-agenda singular voice ----------------------------------------------------


def test_day_agenda_voice_singular():
    line = fallback_day_agenda_voice(
        [{"title": "Trivia Night", "location_name": "Mudshark"}],
        date(2026, 7, 7),
    )
    assert "one thing" in line
    assert "one things" not in line


# --- /today water-temp attribution ------------------------------------------------


def test_today_water_temp_echoes_upstream_attribution(monkeypatch):
    from app.conditions import today_payload as tp
    from app.db.database import SessionLocal

    monkeypatch.setattr(
        tp,
        "build_conditions_api_payload",
        lambda db, now=None: {
            "water_temp_f": 82.0,
            "water_temp_attribution": "RISE Parker Dam",
        },
    )
    with SessionLocal() as db:
        payload = tp.build_today_payload(db)
    field = next(f for f in payload["fields"] if f.key == "water_temp")
    assert field.attribution == "RISE Parker Dam"


# --- NWS multi-zone alerts ----------------------------------------------------------


def test_nws_alerts_fetches_city_and_lake_zones(monkeypatch):
    from app.conditions import nws

    monkeypatch.delenv("LHC_NWS_ZONE_ID", raising=False)
    calls: list[str] = []

    def fake_get(path: str, **kw):
        calls.append(path)
        if "AZZ036" in path:
            return {
                "features": [
                    {
                        "id": "alert-1",
                        "properties": {
                            "event": "Lake Wind Advisory",
                            "headline": "Lake Wind Advisory until 8 PM",
                            "severity": "Moderate",
                        },
                    }
                ]
            }
        return {"features": []}

    monkeypatch.setattr(nws, "_get", fake_get)
    out = nws.fetch_nws_alerts_lhc_zone()
    assert any("AZZ002" in c for c in calls)
    assert any("AZZ036" in c for c in calls)
    assert [a["event"] for a in out["alerts"]] == ["Lake Wind Advisory"]


def test_nws_alerts_dedupes_cross_zone_alert(monkeypatch):
    from app.conditions import nws

    monkeypatch.setenv("LHC_NWS_ZONE_ID", "AZZ002,AZZ036")
    feature = {
        "id": "alert-both",
        "properties": {"event": "High Wind Warning", "headline": "High Wind Warning"},
    }

    monkeypatch.setattr(nws, "_get", lambda path, **kw: {"features": [feature]})
    out = nws.fetch_nws_alerts_lhc_zone()
    assert len(out["alerts"]) == 1


# --- lake-date anchors ----------------------------------------------------------------


def test_extract_date_uses_lake_wallclock(monkeypatch):
    from app.core import extraction

    # 2026-07-04 20:00 Phoenix == 2026-07-05 03:00 UTC: a UTC host's
    # date.today() has already rolled to the 5th.
    fixed = datetime(2026, 7, 4, 20, 0, tzinfo=ZoneInfo("America/Phoenix"))
    monkeypatch.setattr(extraction, "now_lake_havasu", lambda: fixed)
    assert extraction._extract_date("something today") == "2026-07-04"
    assert extraction._extract_date("something tomorrow") == "2026-07-05"


def test_weekend_digest_defaults_to_lake_date(monkeypatch):
    from app.digest import builder

    fixed = datetime(2026, 7, 3, 18, 30, tzinfo=ZoneInfo("America/Phoenix"))  # Friday evening
    monkeypatch.setattr(builder, "now_lake_havasu", lambda: fixed)
    captured: dict = {}

    def fake_window(chip, *, today):
        captured["today"] = today
        return today, today

    monkeypatch.setattr(builder, "event_window_for_chip", fake_window)
    monkeypatch.setattr(builder, "events_in_window", lambda *a, **k: [])
    monkeypatch.setattr(builder, "saved_venue_events_for_user", lambda *a, **k: [])
    builder.build_weekend_digest(db=None, user_id="u1")
    # Still Friday in Phoenix — a UTC anchor would have been Saturday.
    assert captured["today"] == date(2026, 7, 3)
