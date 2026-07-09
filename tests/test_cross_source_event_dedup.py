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
from datetime import date, time

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.dedup import (
    dedup_cross_source_event_rows,
    dedup_cross_source_occurrences,
)
from app.home import sandstone

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
    # §3B: the survivor ABSORBS twins' fields, but a curated/authoritative row
    # must NOT have its own description replaced by a longer aggregator blurb.
    assert kept[0].description == "Free swim, noon-4."


# --- Item §3B: survivor absorbs the dropped twin's best display fields --------


def test_survivor_absorbs_dropped_twin_flyer() -> None:
    """The higher-priority row wins the sort but has no flyer; it absorbs the
    dropped twin's poster image so the one rendered row still shows it."""
    survivor = _ev("Beach Concert", start=time(19, 0), venue="The Nautical",
                   source="go_lake_havasu", ev_id="surv")  # src 1, no image
    loser = _ev("Beach Concert", start=time(19, 0), venue="The Nautical",
                source="river_scene_import", ev_id="lose")  # src 4, has flyer
    loser.image_url = "https://cdn.example/flyer.jpg"
    kept = dedup_cross_source_event_rows([survivor, loser])
    assert kept == [survivor]
    assert kept[0].image_url == "https://cdn.example/flyer.jpg"  # absorbed


def test_calvary_relaxed_venue_guard_collapses_and_absorbs_richest_desc() -> None:
    """The Calvary miss: two feeds describe one 6 PM event under subset titles at
    unrelated venue strings (street address vs short name) — different sources,
    both specific venues, EXACT same start. The relaxed guard (drops _venue_match
    when subset-title + exact-time + diff-source) collapses them to one, and the
    survivor absorbs the richer (longer) description."""
    long_desc = (
        "Calvary Baptist Church Sweetwater Campus invites the whole community to a "
        "free 4th of July Family Water Night with inflatable slides, games, food, "
        "and fireworks viewing from the lawn. Bring a towel and a chair."
    )
    rs = _ev(
        "Calvary Baptist Church (Sweetwater Campus) 4th of July Family Water Night",
        start=time(18, 0), venue="3100 Sweetwater Ave LHC",  # address = specific, digit-led
        desc=long_desc, source="river_scene_import", ev_id="rs",
    )
    gl = _ev(
        "Family Water Night at Calvary",
        start=time(18, 0), end=time(20, 0), venue="Calvary",  # short name = named place
        desc="Family Water Night.", source="go_lake_havasu", ev_id="gl",
    )
    kept = dedup_cross_source_event_rows([rs, gl])
    assert len(kept) == 1
    survivor = kept[0]
    assert survivor.id == "gl"  # named venue + higher source priority
    assert survivor.description == long_desc  # absorbed the richer text
    # §3.1: the bare "Calvary" survivor also absorbs the twin's street address.
    assert survivor.location_name == "3100 Sweetwater Ave LHC"


def test_named_venue_survivor_not_downgraded_to_address() -> None:
    """§3.1 guard: a real multi-word named venue is NEVER replaced by a twin's raw
    street address — only a bare one-word venue ("Calvary") is upgraded."""
    named = _ev("Lake Havasu Farmers Market", start=time(8, 0), end=time(12, 0),
                venue="Go Lake Havasu Visitor Center", source="go_lake_havasu", ev_id="named")
    addressed = _ev("Lake Havasu Farmers Market", start=time(8, 0),
                    venue="2144 McCulloch Blvd N Lake Havasu City, AZ 86403",
                    source="river_scene_import", ev_id="addr")
    kept = dedup_cross_source_event_rows([named, addressed])
    assert len(kept) == 1
    assert kept[0].id == "named"
    assert kept[0].location_name == "Go Lake Havasu Visitor Center"  # not downgraded


def test_relaxed_guard_still_requires_subset_titles() -> None:
    """The relaxation is gated on the title-subset signal: two DIFFERENT events at
    different specific venues that merely share an exact start time (no title
    subset) are never merged."""
    a = _ev("Sunrise Yoga", start=time(6, 0), venue="Rotary Park",
            source="admin", ev_id="a")
    b = _ev("Chamber Breakfast", start=time(6, 0), venue="The Nautical",
            source="go_lake_havasu", ev_id="b")
    kept = dedup_cross_source_event_rows([a, b])
    assert len(kept) == 2


def test_absorb_is_read_only_and_never_persists() -> None:
    """CRITICAL (read-only contract): the render-time absorb sets display fields
    via set_committed_value, so even a COMMIT on the session must not write the
    grafted flyer back to the survivor's DB row."""
    suffix = uuid.uuid4().hex[:6]
    title = f"ZZ Absorb Safety {suffix}"
    day = date(2099, 10, 10)
    eids: list[str] = []
    with SessionLocal() as db:
        surv = Event(
            title=title, normalized_title=title.lower(), date=day,
            start_time=time(19, 0), end_time=None, location_name="The Nautical",
            location_normalized="the nautical", description="short",
            event_url="https://example.com/e", tags=[], status="live",
            source="go_lake_havasu", verified=True,
        )
        lose = Event(
            title=title, normalized_title=title.lower(), date=day,
            start_time=time(19, 0), end_time=None, location_name="The Nautical",
            location_normalized="the nautical", description="short",
            event_url="https://example.com/e", tags=[], status="live",
            source="river_scene_import", image_url="https://cdn.example/flyer.jpg",
            verified=True,
        )
        db.add(surv)
        db.add(lose)
        db.flush()
        surv_id = surv.id
        eids += [surv.entity_id, lose.entity_id]
        db.commit()
    try:
        with SessionLocal() as db:
            rows = list(
                db.scalars(select(Event).where(Event.entity_id.in_(eids))).all()
            )
            kept = dedup_cross_source_event_rows(rows)
            # In memory the survivor shows the absorbed flyer...
            assert len(kept) == 1
            assert kept[0].image_url == "https://cdn.example/flyer.jpg"
            db.commit()  # would persist any dirty attribute
        # ...but the survivor's DB row was never written.
        with SessionLocal() as db:
            fresh = db.get(Event, surv_id)
            assert fresh is not None
            assert fresh.image_url is None
    finally:
        _cleanup(eids)


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
