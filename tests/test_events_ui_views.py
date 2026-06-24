"""/events-ui redesign — Today accordion, Week rollups, Month grid, day detail.

One concept at three zoom levels: the Today/day view groups events into a
category accordion (Events / Music & nightlife / Lake Life / Fitness &
classes), the Week view shows the top one-off headline + honest per-group
rollups, and the Month view is a Sunday-anchored date-picker grid whose counts
are one-offs only (B-02 alignment regression pinned here).

Patterns mirror tests/test_events_ui_freshness.py: far-future 2099 dates, uuid
suffixes, targeted cleanup, and ``app.home.router.now_lake_havasu`` monkeypatch
for views anchored on "today". Class counts from real venue Schedule rows can
leak into any window, so assertions on the classes group are presence/at-least,
never exact-global.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.main import app

_LHC = ZoneInfo("America/Phoenix")

# 2099-07-13 is a Monday (2099-06-07 is a Sunday — see test_events_ui_freshness).
_MONDAY = datetime(2099, 7, 13, 9, 0, tzinfo=_LHC)


def _add_event(
    db,
    *,
    title: str,
    on: date,
    start: time | None,
    loc: str,
    tags=None,
    recurring: bool = False,
) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=None,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=tags or [],
        status="live",
        source="test-events-views",
        verified=True,
        is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


# --- (a) Today view: category accordion, Events first + open, counts ---------


def test_today_view_groups_by_category_events_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:6]
    day = _MONDAY.date()
    festival = f"ZZ Festival {suffix}"
    stroll = f"ZZ Gallery Stroll {suffix}"
    band = f"ZZ Live Band Night {suffix}"
    paddle = f"ZZ Sunset Paddle {suffix}"
    swim = f"ZZ Lap Swim {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=festival, on=day, start=time(18, 0), loc="Bridge",
                               tags=["festival"]))
        eids.append(_add_event(db, title=stroll, on=day, start=time(17, 0), loc="Main St"))
        eids.append(_add_event(db, title=band, on=day, start=time(20, 0), loc="Bar",
                               tags=["music"]))
        # Evening times so the same-day auto-expiry (Item 6: drop items finished
        # >1h ago) doesn't trim them before the 9 AM mocked "now".
        eids.append(_add_event(db, title=paddle, on=day, start=time(19, 0), loc="Beach"))
        eids.append(_add_event(db, title=swim, on=day, start=time(19, 30), loc="Pool",
                               recurring=True))
        db.commit()
    try:
        monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _MONDAY)
        with TestClient(app) as client:
            body = client.get("/events-ui").text
        i_events = body.index('data-group="events"')
        i_music = body.index('data-group="music"')
        i_water = body.index('data-group="water"')
        i_classes = body.index('data-group="classes"')
        # Owner-approved group order; the recurring Lap Swim is a pool session →
        # Fitness & classes (no separate Aquatic Center group).
        assert i_events < i_music < i_water < i_classes
        # "Events" is expanded by default; the rest load collapsed.
        assert 'data-group="events" open' in body
        for key in ("music", "water", "classes"):
            assert f'data-group="{key}" open' not in body
        # Right members + an honest count pill on the Events group.
        events_block = body[i_events:i_music]
        assert festival in events_block and stroll in events_block
        assert 'ev-acc-count">2<' in events_block
        assert band in body[i_music:i_water]
        # Sunset Paddle is genuinely on the lake → On-the-water group.
        assert paddle in body[i_water:i_classes]
        # Lap Swim is a pool class → Fitness & classes, not On-the-water.
        assert swim in body[i_classes:]
    finally:
        _cleanup(eids)


# --- (b) classes never land in the Events group ------------------------------


def test_classes_never_appear_in_events_group() -> None:
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 7, 14)  # Tuesday after _MONDAY
    spin = f"ZZ Spin Class {suffix}"  # recurring class event (gym, not pool)
    yoga = f"ZZ Yoga Workshop {suffix}"  # one-off, but class-tier
    gala = f"ZZ Quilt Gala {suffix}"  # plain one-off
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=spin, on=day, start=time(8, 0), loc="Gym",
                               tags=["class"], recurring=True))
        eids.append(_add_event(db, title=yoga, on=day, start=time(9, 0), loc="Studio"))
        eids.append(_add_event(db, title=gala, on=day, start=time(18, 0), loc="Hall"))
        db.commit()
    try:
        with TestClient(app) as client:
            body = client.get(f"/events-ui?date={day.isoformat()}").text
        i_events = body.index('data-group="events"')
        i_classes = body.index('data-group="classes"')
        events_block = body[i_events:i_classes]
        assert gala in events_block
        assert spin not in events_block and yoga not in events_block
        classes_block = body[i_classes:]
        assert spin in classes_block and yoga in classes_block
        # P1: the inconsistent "recurring" row banner is removed across all views.
        assert "Runs regularly" not in classes_block
        assert "Recurring ↻" not in classes_block
    finally:
        _cleanup(eids)


# --- (b2) Kids & Family collector + pool classes split ----------------------


def test_family_and_pool_classes_split_out() -> None:
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 7, 21)  # a Tuesday
    karate = f"ZZ Youth Karate {suffix}"     # kid class -> Kids & Family
    openswim = f"ZZ Open Swim {suffix}"      # pool + family -> Kids & Family
    adultlap = f"ZZ Adult Lap Swim {suffix}"  # pool, adult -> Fitness & classes
    aqua = f"ZZ Aqua Aerobics {suffix}"      # pool -> Fitness & classes
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=karate, on=day, start=time(16, 0), loc="Dojo",
                               recurring=True))
        eids.append(_add_event(db, title=openswim, on=day, start=time(12, 0), loc="Pool",
                               recurring=True))
        eids.append(_add_event(db, title=adultlap, on=day, start=time(5, 0), loc="Pool",
                               recurring=True))
        eids.append(_add_event(db, title=aqua, on=day, start=time(8, 0), loc="Pool",
                               recurring=True))
        db.commit()
    try:
        with TestClient(app) as client:
            body = client.get(f"/events-ui?date={day.isoformat()}").text
        i_events = body.index('data-group="events"')
        i_family = body.index('data-group="family"')
        i_classes = body.index('data-group="classes"')
        events_block = body[i_events : body.index("</details>", i_events)]
        family_block = body[i_family : body.index("</details>", i_family)]
        classes_block = body[i_classes : body.index("</details>", i_classes)]
        # Kids & Family collects kid occurrences. Open Swim (non-class) re-lists
        # here AND stays in its primary group (additive overlay, discoverability).
        assert karate in family_block and openswim in family_block
        assert adultlap not in family_block and aqua not in family_block
        # P1 age-awareness: a YOUTH class routes to Kids & Family ONLY — it is no
        # longer duplicated into the adult Fitness list. Adult classes still list.
        assert karate not in classes_block
        assert adultlap in classes_block and aqua in classes_block
        # Open Swim is all-day drop-in rec -> "Happening today" (events), not a class.
        assert openswim in events_block
        assert openswim not in classes_block
    finally:
        _cleanup(eids)


# --- (c) Week view: rollup counts + top one-off headline ----------------------


def test_week_view_rollup_counts_and_headline(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = uuid.uuid4().hex[:6]
    wednesday = date(2099, 7, 15)
    parade = f"ZZ Big Parade {suffix}"  # special tier — must headline
    quilt = f"ZZ Quilt Show {suffix}"  # other tier one-off
    karaoke = f"ZZ Karaoke Night {suffix}"  # music tier one-off
    spin = f"ZZ Spin Class {suffix}"  # recurring — never a headline
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=parade, on=wednesday, start=time(18, 0), loc="Main St"))
        eids.append(_add_event(db, title=quilt, on=wednesday, start=time(10, 0), loc="Hall"))
        eids.append(_add_event(db, title=karaoke, on=wednesday, start=time(19, 0), loc="Bar"))
        eids.append(_add_event(db, title=spin, on=wednesday, start=time(6, 0), loc="Gym",
                               recurring=True))
        db.commit()
    try:
        monkeypatch.setattr("app.home.router.now_lake_havasu", lambda: _MONDAY)
        with TestClient(app) as client:
            body = client.get("/events-ui?view=week").text
        row_start = body.index(f"date={wednesday.isoformat()}")
        row = body[row_start : body.index("</a>", row_start)]
        # Headline is the top-ranked ONE-OFF (special parade), with its time.
        assert parade in row
        assert "6 PM ·" in row
        # Counts per group (zero groups omitted); only the headline is named.
        assert "2 events" in row
        assert "1 music" in row
        # Recurring spin lands in the class rollup (+ any real venue
        # schedules), so assert a counted "N class(es)" token — a bare
        # "class" substring would match HTML attributes.
        assert re.search(r"\d+ class", row)
        assert quilt not in row and karaoke not in row and spin not in row
    finally:
        _cleanup(eids)


def test_week_rollup_counts_match_day_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    """The week rollup must count an occurrence under the SAME group the day view
    renders it in. Regression for the carried-forward finding: a senior class
    counted under "classes" in the week strip but rendered under Seniors in the
    day view, so the two disagreed. With the shared router they agree."""
    from app.home import events_views as ev_views

    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 7, 15)  # a Wednesday inside the _MONDAY week window
    senior_yoga = f"ZZ Senior Chair Yoga {suffix}"  # senior + class -> Seniors only
    parade = f"ZZ Parade {suffix}"  # plain one-off -> Happening today
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(
            _add_event(
                db, title=senior_yoga, on=day, start=time(9, 0), loc="Senior Center",
                tags=["senior"], recurring=True,
            )
        )
        eids.append(_add_event(db, title=parade, on=day, start=time(18, 0), loc="Main St"))
        db.commit()
    try:
        with SessionLocal() as db:
            groups = ev_views.day_groups(db, day=day)
            week = ev_views.week_rows(db, start=day, days=1)
        rendered = {g["key"]: g["count"] for g in groups}
        counts = week[0]["counts"]
        # The senior class lands under Seniors in BOTH — never inflates "classes".
        assert rendered.get("seniors", 0) >= 1
        assert counts.get("seniors", 0) == rendered.get("seniors", 0)
        assert counts.get("classes", 0) == rendered.get("classes", 0)
        assert counts.get("events", 0) == rendered.get("events", 0)
    finally:
        _cleanup(eids)


def test_youth_bmx_routes_to_fitness_sports_and_family():
    """Casey 2026-06-24: BMX racing belongs under Fitness & sports. A youth-tagged
    BMX race keeps its sports primary AND re-lists under Kids & Family (additive),
    unlike a youth instructional class which routes to Kids & Family only."""
    from app.home.events_views import _occurrence_group_keys

    bmx = _occurrence_group_keys(
        "classes", title="BMX Local Race", venue=None, activity=None,
        is_family=True, is_senior=False,
    )
    assert "classes" in bmx and "family" in bmx
    # A youth instructional class is unchanged — Kids & Family only.
    dance = _occurrence_group_keys(
        "classes", title="Tiny Toes Ballet", venue=None, activity="Dance",
        is_family=True, is_senior=False,
    )
    assert dance == ["family"]


def test_fitness_group_label_is_sports():
    from app.home.event_buckets import GROUP_DEFS

    labels = {k: label for k, label, _icon in GROUP_DEFS}
    assert labels["classes"] == "Fitness & sports"


# --- (d) Month grid: weekday alignment (B-02) + one-off-only counts ----------


def test_month_grid_first_of_month_in_correct_weekday_column() -> None:
    """B-02 regression: July 1, 2099 is a Wednesday, so the Sunday-anchored
    grid must lead with exactly three blank cells (Sun/Mon/Tue) before it."""
    assert date(2099, 7, 1).weekday() == 2  # sanity: Wednesday (Mon=0)
    with TestClient(app) as client:
        body = client.get("/events-ui?view=month&cal=2099-07").text
    assert "July 2099" in body
    head = body[: body.index("date=2099-07-01")]
    assert head.count("ev-mg-cell blank") == 3
    # Sunday-first weekday header.
    assert body.index("<span>Sun</span>") < body.index("<span>Mon</span>")


def test_month_grid_counts_oneoffs_only_with_class_badge() -> None:
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 7, 22)
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=f"ZZ Lone Gala {suffix}", on=day,
                               start=time(18, 0), loc="Hall"))
        eids.append(_add_event(db, title=f"ZZ Repeat Drill {suffix}", on=day,
                               start=time(6, 0), loc="Gym", recurring=True))
        db.commit()
    try:
        with TestClient(app) as client:
            body = client.get("/events-ui?view=month&cal=2099-07").text
        cell_start = body.index(f"date={day.isoformat()}")
        cell = body[cell_start : body.index("</a>", cell_start)]
        # One-off count stays 1 — the recurring row lands in the class badge,
        # never the event count (no titles in cells: it's a date picker).
        assert 'ev-mg-ct">1<' in cell
        assert "ev-mg-dot" in cell
        assert f"ZZ Lone Gala {suffix}" not in body
    finally:
        _cleanup(eids)


# --- (e) ?date= renders the accordion + day navigation ------------------------


def test_date_view_renders_accordion_with_day_nav() -> None:
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 7, 25)  # a Saturday
    title = f"ZZ Sat Market {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=title, on=day, start=time(8, 0), loc="Plaza"))
        db.commit()
    try:
        with TestClient(app) as client:
            body = client.get(f"/events-ui?date={day.isoformat()}").text
        assert "Showing events for" in body and "Saturday, July 25" in body
        assert 'data-group="events"' in body and title in body
        assert "/events-ui?date=2099-07-24" in body  # prev day
        assert "/events-ui?date=2099-07-26" in body  # next day
        assert "Back to today" in body
    finally:
        _cleanup(eids)


# --- (g) Time TBD rows render honestly and sort last --------------------------


def test_time_tbd_rows_render_label_and_sort_last() -> None:
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 7, 27)
    timed = f"ZZ Timed Talk {suffix}"
    tbd = f"ZZ Mystery Gala {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=timed, on=day, start=time(10, 0), loc="Hall"))
        # start_time is NOT NULL by schema; time-unknown events are stored as
        # the bare-midnight ingest fallback, which is_time_tbd() detects.
        eids.append(_add_event(db, title=tbd, on=day, start=time(0, 0), loc="Hall"))
        db.commit()
    try:
        with TestClient(app) as client:
            body = client.get(f"/events-ui?date={day.isoformat()}").text
        # Scope to the Events group block so stray venue-schedule rows
        # elsewhere on the page can't skew the assertions.
        i_events = body.index('data-group="events"')
        block = body[i_events : body.index("</details>", i_events)]
        assert "Time TBD" in block  # honest label, never a fabricated 12 AM
        assert "12 AM" not in block
        assert "10 AM" in block  # the timed sibling keeps its real time
        # TBD rows sort after timed rows within their group.
        assert block.index(tbd) > block.index(timed)
    finally:
        _cleanup(eids)
