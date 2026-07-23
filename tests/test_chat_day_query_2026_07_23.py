"""Chat "what's on <day>" pipeline fixes (site sweep 2026-07-23).

Live repro that drove these tests: POST /api/chat "whats happening saturday"
(asked on Thursday, July 23) answered "This week's busy — 24 things across two
days" with a week strip anchored on TODAY, Thursday's agenda open, Sat/Sun
showing 0 events — plus "12 am" rows for midnight-fallback times and titles
echoing their venue ("Pickleball Open Play – Mike Delaney …").

Four root causes, each covered here:

1. ``resolver._event_window`` threw away ``extract_date_range``'s parsed dates
   (bare "range" token; no branch in ``_event_window_dates``) → the asked-for
   day was ignored and the window fell back to today+30.
2. ``_query_events``' flat 24-row chronological cap: the window's first day
   (~19 recurring rec/senior rows) exhausted the budget → later days rendered
   "0 events" and one-off events beyond ~tomorrow never appeared in chat.
3. ``_event_to_row`` forwarded the raw 00:00 ingest fallback → JS drew "12 am"
   under Morning (the /home day view shows "All day" / "Time TBD").
4. No title/venue cleaning on the chat row path.

Plus the naive-datetime write in ``merge_scraper_into_event`` (scraped_at is a
TZAwareDateTime column, which raises on naive datetimes at flush).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from app.chat.component_builders import _event_to_agenda_item
from app.chat.intents.queries import (
    _cap_rows_per_day,
    _event_to_row,
    _event_window_dates,
    _query_events,
)
from app.chat.intents.resolver import _event_window
from app.core import slots as slots_mod
from app.core.slots import extract_date_range

THURSDAY = date(2026, 7, 23)  # the live-repro "today": a Thursday
SATURDAY = date(2026, 7, 25)


@pytest.fixture
def frozen_today(monkeypatch):
    """Pin app.core.slots' clock to Thursday 2026-07-23 (Lake Havasu)."""
    fixed = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
    monkeypatch.setattr(slots_mod, "now_lake_havasu", lambda: fixed)
    return THURSDAY


# ─────────── 1. extract_date_range: weekday + month-day phrasings ───────────


def test_bare_weekday_resolves_to_next_occurrence(frozen_today) -> None:
    dr = extract_date_range("whats happening saturday")
    assert dr == {"start": SATURDAY, "end": SATURDAY}


def test_month_day_resolves_to_exact_date(frozen_today) -> None:
    dr = extract_date_range("events on July 25")
    assert dr == {"start": SATURDAY, "end": SATURDAY}


def test_month_day_with_year_and_ordinal(frozen_today) -> None:
    dr = extract_date_range("what's on july 25th, 2026")
    assert dr == {"start": SATURDAY, "end": SATURDAY}


def test_month_day_beats_weekday_word(frozen_today) -> None:
    # Tier2-parser priority: a full calendar day wins over its weekday word.
    dr = extract_date_range("Friday, July 31")
    assert dr == {"start": date(2026, 7, 31), "end": date(2026, 7, 31)}


def test_past_yearless_month_day_rolls_to_next_year(frozen_today) -> None:
    dr = extract_date_range("events on January 5")
    assert dr == {"start": date(2027, 1, 5), "end": date(2027, 1, 5)}


def test_clock_phrasing_is_not_a_date(frozen_today) -> None:
    # "may 8pm" is a time, not May 8. (No other date signal → None.)
    assert extract_date_range("open until may 8pm") is None


def test_first_friday_still_excluded(frozen_today) -> None:
    # Regression: "First Friday" is an event name, not a day filter.
    assert extract_date_range("first friday events") is None


# ─────────── 2. resolver window token carries the parsed dates ───────────


def test_event_window_encodes_range_token(frozen_today) -> None:
    assert _event_window("whats happening saturday") == "range:2026-07-25:2026-07-25"


def test_event_window_keyword_ladder_unchanged(frozen_today) -> None:
    assert _event_window("whats on this weekend") == "this_weekend"
    assert _event_window("what should i do when it's too hot") == "upcoming"


def test_event_window_dates_parses_range_token() -> None:
    assert _event_window_dates("range:2026-07-25:2026-07-25", THURSDAY) == (
        SATURDAY,
        SATURDAY,
    )
    assert _event_window_dates("range:2026-07-24:2026-07-26", THURSDAY) == (
        date(2026, 7, 24),
        date(2026, 7, 26),
    )


def test_event_window_dates_malformed_range_falls_back() -> None:
    start, end = _event_window_dates("range:garbage", THURSDAY)
    assert start == THURSDAY and (end - start).days == 30


# ─────────── 3. per-day fair cap ───────────


def _mk_row(d: date, i: int) -> dict:
    return {"type": "event", "name": f"E{i}", "date": d.isoformat()}


def test_cap_rows_per_day_keeps_later_days() -> None:
    rows = [_mk_row(THURSDAY, i) for i in range(19)]
    rows += [_mk_row(date(2026, 7, 24), i) for i in range(5)]
    rows += [_mk_row(SATURDAY, i) for i in range(15)]
    capped = _cap_rows_per_day(rows, 12)
    by_day: dict[str, int] = {}
    for r in capped:
        by_day[r["date"]] = by_day.get(r["date"], 0) + 1
    # The old flat cap returned 19+5 and NOTHING for Saturday.
    assert by_day == {"2026-07-23": 12, "2026-07-24": 5, "2026-07-25": 12}
    # Chronological order preserved.
    assert [r["date"] for r in capped] == sorted(r["date"] for r in capped)


class _FakeEvent:
    def __init__(self, title: str, d: date, start: time | None, end: time | None = None):
        self.title = title
        self.date = d
        self.start_time = start
        self.end_time = end
        self.end_date = None
        self.location_name = "Venue"
        self.description = ""
        self.tags: list[str] = []
        self.event_url = "https://example.com/e"


def test_query_events_multi_day_window_reaches_saturday(monkeypatch) -> None:
    """End-to-end through _query_events: Saturday survives a Thu-anchored window."""
    fri = date(2026, 7, 24)
    pairs = (
        [(_FakeEvent(f"Thu {i}", THURSDAY, time(8, 0)), THURSDAY) for i in range(19)]
        + [(_FakeEvent(f"Fri {i}", fri, time(9, 0)), fri) for i in range(5)]
        + [(_FakeEvent("Troy's Alligator Feed", SATURDAY, time(15, 0)), SATURDAY)]
    )
    seen_limits: list[int] = []

    def fake_events_in_window(db, *, window_start, window_end, limit, **kw):
        seen_limits.append(limit)
        return [(e, occ) for e, occ in pairs if window_start <= occ <= window_end]

    import app.events.queries as eq

    monkeypatch.setattr(eq, "events_in_window", fake_events_in_window)
    rows = _query_events(None, "range:2026-07-23:2026-07-29", today=THURSDAY, activity=None)
    sat_rows = [r for r in rows if r["date"] == "2026-07-25"]
    assert [r["name"] for r in sat_rows] == ["Troy's Alligator Feed"]
    # Multi-day windows fetch deeper than the old flat 24.
    assert seen_limits and seen_limits[0] > 24
    # …and no single day exceeds the per-day cap.
    by_day: dict[str, int] = {}
    for r in rows:
        by_day[r["date"]] = by_day.get(r["date"], 0) + 1
    assert max(by_day.values()) <= 12


def test_query_events_single_day_window_unchanged_limit(monkeypatch) -> None:
    def fake_events_in_window(db, *, window_start, window_end, limit, **kw):
        assert limit == 24  # single-day keeps the original budget
        return [(_FakeEvent("Sat thing", SATURDAY, time(10, 0)), SATURDAY)]

    import app.events.queries as eq

    monkeypatch.setattr(eq, "events_in_window", fake_events_in_window)
    rows = _query_events(None, "range:2026-07-25:2026-07-25", today=THURSDAY, activity=None)
    assert [r["date"] for r in rows] == ["2026-07-25"]


# ─────────── 4. row + agenda-item display contract ───────────


def test_event_to_row_tbd_midnight_gets_label_not_12am() -> None:
    ev = _FakeEvent("Pickleball Open Play", SATURDAY, time(0, 0), None)
    row = _event_to_row(ev, SATURDAY)
    assert row["start_time"] is None
    assert row["time_label"] == "All day"  # open-play rec reads all-day, per /home


def test_event_to_row_drop_in_label() -> None:
    ev = _FakeEvent("Open Gym", SATURDAY, time(0, 0), None)
    row = _event_to_row(ev, SATURDAY)
    assert row["start_time"] is None
    assert row["time_label"] == "Drop-in — call for hours"


def test_event_to_row_real_time_passes_through() -> None:
    ev = _FakeEvent("Troy's Alligator Feed", SATURDAY, time(15, 0), time(16, 0))
    row = _event_to_row(ev, SATURDAY)
    assert row["start_time"] == "15:00"
    assert row["end_time"] == "16:00"
    assert "time_label" not in row


def test_event_to_row_strips_venue_suffix_title() -> None:
    ev = _FakeEvent("Pickleball Open Play – The Ark Center", SATURDAY, time(8, 0))
    ev.location_name = "The Ark Center"
    row = _event_to_row(ev, SATURDAY)
    assert row["name"] == "Pickleball Open Play"


def test_agenda_item_passes_time_label_through() -> None:
    item = _event_to_agenda_item(
        {
            "type": "event",
            "name": "Pickleball Open Play",
            "date": "2026-07-25",
            "start_time": None,
            "end_time": None,
            "location_name": "Mike Delaney Pickleball Complex",
            "time_label": "All day",
            "tags": [],
        }
    )
    assert item.get("start") is None
    assert item["time_label"] == "All day"


def test_agenda_item_derives_label_when_producer_omits_it() -> None:
    # tier2's event_dict nulls TBD starts but sends no label — derive one.
    item = _event_to_agenda_item(
        {
            "type": "event",
            "name": "Pickleball Open Play",
            "date": "2026-07-25",
            "start_time": None,
            "end_time": None,
            "location_name": "The Ark Center",
            "tags": [],
        }
    )
    assert item["time_label"] == "All day"


def test_agenda_item_cleans_venue_echo_title() -> None:
    item = _event_to_agenda_item(
        {
            "type": "event",
            "name": "Pickleball Open Play – The Ark Center",
            "date": "2026-07-25",
            "start_time": "08:00",
            "end_time": None,
            "location_name": "The Ark Center",
            "tags": [],
        }
    )
    assert item["title"] == "Pickleball Open Play"


# ─────────── 5. merge_scraper_into_event writes aware scraped_at ───────────


def test_merge_scraper_scraped_at_is_aware_and_flushable() -> None:
    from app.db.database import SessionLocal
    from app.db.entity_dual_write import create_event_and_entity
    from app.db.models import Event
    from app.events.dedup import merge_scraper_into_event
    from app.events.scrapers.base import EventPayload

    with SessionLocal() as db:
        ev = Event(
            title="Museum Lecture",
            normalized_title="museum lecture",
            date=SATURDAY,
            start_time=time(18, 0),
            location_name="Museum of History",
            location_normalized="museum of history",
            description="",
            event_url="https://example.com/lecture",
            status="live",
            source="museum_events",
        )
        db.add(ev)
        create_event_and_entity(db, ev)
        db.flush()
        payload = EventPayload(
            name="Museum Lecture",
            description="Updated description",
            start_date=SATURDAY,
            start_time=time(18, 0),
            event_url="https://example.com/lecture2",
        )
        merge_scraper_into_event(db, ev, payload, scrape_source="museum_events")
        # The old naive ``datetime.now(UTC).replace(tzinfo=None)`` made this
        # flush raise ValueError from the TZAwareDateTime bind check.
        db.flush()
        assert ev.scraped_at is not None
        assert ev.scraped_at.tzinfo is not None
        db.rollback()
