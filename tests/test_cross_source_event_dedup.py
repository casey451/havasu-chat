"""Render-time cross-source event dedup (app/events/dedup.py + display paths).

Two scrape sources carry the same real-world event with cosmetic differences:
one stores the street address as the venue and fabricates a noon start, the
other has the named venue and the real time; titles can differ only by a curly
apostrophe. The render-time helper collapses such twins per (normalized title,
date) -- keeping the really-timed, named-venue survivor -- while NEVER merging
two events with real start times >2h apart (legit matinee/evening sessions).

Pure-helper tests build unattached Event rows; surface tests mirror the WP-3
pattern (far-future dates, targeted cleanup) over the home week strip, the
month calendar, and the /events-ui window feed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.dedup import (
    dedup_cross_source_event_rows,
    dedup_cross_source_occurrences,
)
from app.home import sandstone
from app.home.router import _events_for_window_with_total

_DAY = date(2099, 8, 17)

_NAMED_VENUE = "Go Lake Havasu Visitor Center"
_ADDRESS_VENUE = "2144 McCulloch Blvd N Lake Havasu City, AZ 86403"


def _ev(
    title: str,
    *,
    start: time | None,
    end: time | None = None,
    venue: str = "Test Venue",
    desc: str = "An event",
    source: str = "test_dedup",
    on: date = _DAY,
    ev_id: str = "ev",
) -> Event:
    return Event(
        id=ev_id,
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=end,
        location_name=venue,
        location_normalized=venue.lower(),
        description=desc,
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source=source,
    )


# --- pure helper -------------------------------------------------------------


def test_farmers_market_address_and_fake_noon_collapse_to_real_twin() -> None:
    """The prod symptom: venue-address + fake-noon twin loses to the 8 AM one."""
    real = _ev(
        "Lake Havasu Farmers Market",
        start=time(8, 0),
        end=time(12, 0),
        venue=_NAMED_VENUE,
        ev_id="real",
    )
    fake = _ev(
        "Lake Havasu Farmers Market",
        start=time(12, 0),  # bare fabricated noon, no end time
        venue=_ADDRESS_VENUE,
        ev_id="fake",
    )
    kept = dedup_cross_source_event_rows([fake, real])
    assert kept == [real]


def test_curly_quote_title_matches_and_fake_noon_loses() -> None:
    """The Lady Lee case: curly-apostrophe title, fake-noon TBD vs real 5 PM."""
    fake = _ev(
        "Lady Lee’s Monday Night Dance Party",  # curly apostrophe
        start=time(12, 0),
        ev_id="fake",
    )
    real = _ev(
        "Lady Lee's Monday Night Dance Party",  # straight apostrophe
        start=time(17, 0),
        ev_id="real",
    )
    kept = dedup_cross_source_event_rows([fake, real])
    assert kept == [real]


def test_two_real_times_far_apart_are_separate_sessions() -> None:
    """Guard: same title, both REAL times >2h apart -- matinee + evening kept."""
    matinee = _ev("Havasu Theater Show", start=time(14, 0), end=time(16, 0), ev_id="a")
    evening = _ev("Havasu Theater Show", start=time(19, 0), end=time(21, 0), ev_id="b")
    kept = dedup_cross_source_event_rows([matinee, evening])
    assert kept == [matinee, evening]


def test_two_real_times_within_two_hours_merge_to_named_venue() -> None:
    """Two sources, slightly different real times: one survivor, named venue."""
    addressed = _ev("Sunset Concert", start=time(18, 0), venue="2025 Main St", ev_id="a")
    named = _ev("Sunset Concert", start=time(18, 30), venue="The Nautical", ev_id="b")
    kept = dedup_cross_source_event_rows([addressed, named])
    assert kept == [named]


def test_same_title_different_dates_never_merge() -> None:
    sat = _ev("Lake Havasu Farmers Market", start=time(8, 0), on=date(2099, 8, 22), ev_id="a")
    next_sat = _ev(
        "Lake Havasu Farmers Market", start=time(8, 0), on=date(2099, 8, 29), ev_id="b"
    )
    kept = dedup_cross_source_event_rows([sat, next_sat])
    assert kept == [sat, next_sat]


def test_all_tbd_group_prefers_longer_description() -> None:
    short = _ev("Mystery Gala", start=None, desc="Gala.", ev_id="a")
    rich = _ev("Mystery Gala", start=None, desc="A long, detailed description.", ev_id="b")
    kept = dedup_cross_source_event_rows([short, rich])
    assert kept == [rich]


def test_tiebreak_falls_to_source_priority() -> None:
    """All else equal, the more authoritative EVENT_SOURCE_PRIORITY source wins."""
    low = _ev("Tie Event", start=time(10, 0), source="river_scene_import", ev_id="a")
    high = _ev("Tie Event", start=time(10, 0), source="go_lake_havasu", ev_id="b")
    kept = dedup_cross_source_event_rows([low, high])
    assert kept == [high]


def test_authoritative_source_beats_longer_aggregator_blurb() -> None:
    """The swim-card regression: a curated short admin row outranks a longer
    aggregator blurb when they collapse to one session (source priority now
    sorts ahead of description length)."""
    admin = _ev(
        "Free Swim Day!",
        start=time(12, 0),
        end=time(16, 0),
        venue="Lake Havasu City Aquatic Center",
        desc="Free swim, noon-4.",
        source="admin",
        ev_id="admin",
    )
    aggregator = _ev(
        "Free Swim Day!",
        start=time(13, 0),
        venue="Lake Havasu City Aquatic Center",
        desc="A much longer aggregator blurb describing the free swim event in "
        "great, search-padded detail to make its description win on length.",
        source="go_lake_havasu",
        ev_id="aggregator",
    )
    kept = dedup_cross_source_event_rows([aggregator, admin])
    assert kept == [admin]  # admin (source 0) beats go_lake_havasu (source 1)


def test_occurrence_pairs_keep_input_order_and_distinct_titles() -> None:
    a = _ev("Alpha Night", start=time(19, 0), ev_id="a")
    b = _ev("Beta Brunch", start=time(10, 0), ev_id="b")
    dup = _ev("Alpha Night", start=time(12, 0), ev_id="c")  # fake-noon twin of a
    kept = dedup_cross_source_occurrences([(a, _DAY), (b, _DAY), (dup, _DAY)])
    assert kept == [(a, _DAY), (b, _DAY)]


# --- display surfaces (week strip / month calendar / events-ui feed) ---------


def _seed_farmers_market_pair(db, *, title: str, on: date) -> list[str]:
    """Seed the prod-shaped duplicate pair; returns entity ids for cleanup."""
    eids: list[str] = []
    variants = (
        (time(8, 0), time(12, 0), _NAMED_VENUE, "go_lake_havasu"),
        (time(12, 0), None, _ADDRESS_VENUE, "allevents"),
    )
    for start, end, venue, source in variants:
        ev = Event(
            title=title,
            normalized_title=title.lower(),
            date=on,
            start_time=start,
            end_time=end,
            location_name=venue,
            location_normalized=venue.lower(),
            description="Weekly open-air market.",
            event_url="https://example.com/e",
            tags=[],
            status="live",
            source=source,
            verified=True,
        )
        db.add(ev)
        db.flush()
        eids.append(ev.entity_id)
    db.commit()
    return eids


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def test_week_strip_shows_cross_source_duplicate_once() -> None:
    suffix = uuid.uuid4().hex[:6]
    title = f"ZZ Dedup Farmers Market {suffix}"
    with SessionLocal() as db:
        eids = _seed_farmers_market_pair(db, title=title, on=_DAY)
    try:
        with SessionLocal() as db:
            strip = sandstone.week_strip(db, today=_DAY, per_day=10)
        today_events = strip["days"][0]["events"]
        mine = [e for e in today_events if e["title"] == title]
        assert len(mine) == 1  # one survivor, not two
        assert mine[0]["time"] == "8 AM"  # the real time, never the fake noon
    finally:
        _cleanup(eids)


def test_calendar_month_shows_cross_source_duplicate_once() -> None:
    suffix = uuid.uuid4().hex[:6]
    title = f"ZZ Dedup Cal Market {suffix}"
    day = date(2099, 9, 9)
    with SessionLocal() as db:
        eids = _seed_farmers_market_pair(db, title=title, on=day)
    try:
        with SessionLocal() as db:
            cal = sandstone.calendar_month(db, year=2099, month=9, today=date(2099, 9, 1))
        cell = next(
            c
            for week in cal["weeks"]
            for c in week
            if c.get("in_month") and c.get("day") == day.day
        )
        assert sum(1 for e in cell["events"] if e["title"] == title) == 1
    finally:
        _cleanup(eids)


def test_events_ui_window_feed_dedups_and_keeps_named_venue() -> None:
    """The /events-ui bucket + day-view feed shows one card with the real
    time span and the named venue -- and the honest total counts it once."""
    suffix = uuid.uuid4().hex[:6]
    title = f"ZZ Dedup Feed Market {suffix}"
    day = date(2099, 10, 13)
    win = datetime.combine(day, time(12, 0))
    with SessionLocal() as db:
        eids = _seed_farmers_market_pair(db, title=title, on=day)
    try:
        with SessionLocal() as db:
            rows, _total = _events_for_window_with_total(
                db, start_day=win, end_day=win, limit=16
            )
        mine = [r for r in rows if r["title"] == title]
        assert len(mine) == 1
        assert mine[0]["venue"] == _NAMED_VENUE
        assert mine[0]["time_label"] == "8:00 AM - 12:00 PM"
    finally:
        _cleanup(eids)


# --- Item 2: cross-source SAME-SESSION, DIFFERENT titles ---------------------


def test_cross_source_swim_triple_collapses_to_one() -> None:
    """One real Aquatic Center session surfaced by 3 sources under 3 titles, with
    overlapping times and venue-name variants, collapses to a single survivor."""
    a = _ev("Free Family Swim Sponsored by Abundant Grace", start=time(12, 0),
            end=time(16, 0), venue="Lake Havasu City Aquatic Center",
            source="admin", ev_id="swim-admin")
    b = _ev("Open Swim", start=time(13, 0), end=time(16, 0),
            venue="Aquatic Center", source="allevents", ev_id="swim-allevents")
    c = _ev("Free Swim Day!", start=time(13, 0), end=time(16, 0),
            venue="Aquatic Center", source="go_lake_havasu", ev_id="swim-golake")
    kept = dedup_cross_source_event_rows([a, b, c])
    assert len(kept) == 1


def test_same_source_distinct_swim_sessions_both_kept() -> None:
    """Lap Swim (5 AM) and Open Swim (noon) at the SAME venue/date are genuinely
    distinct sessions — same source AND non-overlapping → both kept."""
    lap = _ev("Lap Swim", start=time(5, 0), end=time(7, 0),
              venue="Lake Havasu City Aquatic Center", source="admin", ev_id="lap")
    openswim = _ev("Open Swim", start=time(12, 0), end=time(16, 0),
                   venue="Lake Havasu City Aquatic Center", source="admin", ev_id="open")
    kept = dedup_cross_source_event_rows([lap, openswim])
    assert len(kept) == 2


def test_cross_source_distinctly_named_activity_events_not_merged() -> None:
    """Two DIFFERENT bowling events at one alley — overlapping, cross-source — stay
    separate because neither title's significant words subset the other's (the
    over-merge the bare overlap+source rule produced)."""
    cosmic = _ev("Cosmic Bowling", start=time(18, 0), end=time(23, 0),
                 venue="Havasu Lanes", source="admin", ev_id="cosmic")
    charity = _ev("Western Arizona Humane Society Back to School Bowl",
                  start=time(18, 0), end=time(21, 0), venue="Havasu Lanes",
                  source="go_lake_havasu", ev_id="charity")
    kept = dedup_cross_source_event_rows([cosmic, charity])
    assert len(kept) == 2


def test_cross_source_subset_titles_but_non_overlapping_kept() -> None:
    """Subset titles + same venue + different sources, but NON-overlapping times
    (morning vs evening) → kept separate (the matinee/evening guard)."""
    morning = _ev("Yoga", start=time(8, 0), end=time(9, 0),
                  venue="Rotary Park", source="admin", ev_id="yoga-am")
    evening = _ev("Sunset Yoga", start=time(18, 0), end=time(19, 0),
                  venue="Rotary Park", source="allevents", ev_id="yoga-pm")
    kept = dedup_cross_source_event_rows([morning, evening])
    assert len(kept) == 2


def test_cross_source_bare_city_venue_not_merged() -> None:
    """Subset titles + overlap + different sources, but the venue is the bare-city
    no-venue fallback → never merged (it isn't a real shared session)."""
    a = _ev("Community Meeting", start=time(9, 0), end=time(11, 0),
            venue="Lake Havasu City", source="legistar", ev_id="bare-a")
    b = _ev("Meeting", start=time(9, 0), end=time(11, 0),
            venue="Lake Havasu City", source="allevents", ev_id="bare-b")
    kept = dedup_cross_source_event_rows([a, b])
    assert len(kept) == 2
