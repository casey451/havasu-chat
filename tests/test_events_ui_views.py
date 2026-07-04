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
from app.home import events_views
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
        i_events = body.index('data-k="events"')
        i_music = body.index('data-k="music"')
        i_water = body.index('data-k="water"')
        # UNIFY (Rule 0b 2026-06-26): one calendar shows the FULL tree — the
        # events / music / on-the-water happenings render in owner-approved order,
        # and the recurring Lap Swim class now renders inline too (the old
        # ?view=places tab is retired). Cleanliness comes from collapse, not a
        # second surface.
        assert i_events < i_music < i_water
        # Session 1 declutter (Casey 2026-07-04): the day loads FULLY COLLAPSED —
        # no top-level section auto-opens, even one holding a real event. The rows
        # still render inside their (closed) <details>, so the order and membership
        # checks below are unaffected; only the `open` attribute is gone.
        for key in ("events", "music", "water"):
            assert f'data-k="{key}" open' not in body
        events_block = body[i_events:i_music]
        assert festival in events_block and stroll in events_block
        assert band in body[i_music:i_water]
        # Sunset Paddle is genuinely on the lake → On-the-water group.
        assert paddle in body[i_water:]
        # Lap Swim is a recurring pool class → now ON the unified Calendar, in the
        # Fitness & Sports group, which is COLLAPSED standing content (no real
        # happening in it → no `open`).
        assert swim in body
        assert 'data-k="classes"' in body
        assert 'data-k="classes" open' not in body
    finally:
        _cleanup(eids)


# --- (b) classes never land in the Events group ------------------------------


def test_classes_appear_collapsed_on_unified_calendar() -> None:
    # UNIFY (Rule 0b 2026-06-26): the calendar shows the FULL tree — recurring
    # classes / class-tier workshops render inline (the ?view=places tab is
    # retired), but in COLLAPSED standing-content sections. A plain happening
    # leads (its group opens); the class rows sit in a collapsed Fitness & Sports
    # group so the day still reads "what's on first".
    suffix = uuid.uuid4().hex[:6]
    day = date(2099, 7, 14)  # Tuesday after _MONDAY
    spin = f"ZZ Spin Class {suffix}"  # recurring class event (gym, not pool)
    yoga = f"ZZ Yoga Workshop {suffix}"  # one-off, but class-tier (activity:yoga)
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
        i_events = body.index('data-k="events"')
        assert gala in body[i_events:]
        # The class rows are now ON the unified Calendar, under a collapsed
        # Fitness & Sports group (standing content never auto-opens).
        assert spin in body and yoga in body
        assert 'data-k="classes"' in body
        assert 'data-k="classes" open' not in body
        # Session 1 declutter (2026-07-04): every top-level section loads collapsed
        # now — the happening's group leads by ORDER, not by auto-open.
        assert 'data-k="events" open' not in body
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
        # These are all recurring classes / drop-in rec — Places & Ongoing
        # content under the two-surface split, not the events-only Calendar. The
        # class-subgroup splitting (incl. the "Youth Martial Arts" peel) lives in
        # the builder's mixed mode, which Phase 3 surfaces on the Places tab; we
        # exercise it directly here (the live Places top-level groups land in
        # Phase 3). Verified via day_groups(events_only=False).
        with SessionLocal() as db:
            groups = events_views.day_groups(db, day=day, events_only=False)
        by_key = {g["key"]: g for g in groups}
        # No Kids & Family group (Casey 2026-06-26): each item appears ONCE.
        assert "family" not in by_key
        classes = by_key["classes"]

        def _walk_rows(node: dict) -> list[dict]:
            out = list(node.get("rows", []) or [])
            for c in node.get("children", []) or []:
                out += _walk_rows(c)
            return out

        def _walk_labels(node: dict) -> list[str]:
            out = [node["label"]] if node.get("label") else []
            for c in node.get("children", []) or []:
                out += _walk_labels(c)
            return out

        classes_titles = [r["title"] for sub in classes.get("subgroups", []) for r in _walk_rows(sub)]
        classes_titles += [r["title"] for r in classes["rows"]]
        sub_labels = [lbl for sub in classes.get("subgroups", []) for lbl in _walk_labels(sub)]
        # Youth nesting (Phase 1): a youth class stays in Fitness & Sports, NESTED as
        # a "Youth Martial Arts" child under its discipline (no flat sibling). Adult
        # pool classes list there too.
        assert any(karate in t for t in classes_titles)
        assert "Youth Martial Arts" in sub_labels
        assert any(adultlap in t for t in classes_titles)
        assert any(aqua in t for t in classes_titles)
        # Open Swim is all-day drop-in rec → Things to Do (events), not a class.
        events_titles = [r["title"] for r in by_key["events"]["rows"]]
        assert any(openswim in t for t in events_titles)
        assert not any(openswim in t for t in classes_titles)
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
        # Two-surface split (spec §1): the Week view is the events-only Calendar —
        # the rollup counts only happenings (events + music here). The recurring
        # Spin class moves to Places & Ongoing and is NOT in the class rollup;
        # no "class" count token appears.
        assert re.search(r"\d+ events", row)
        assert "1 music" in row
        assert not re.search(r"\d+ class", row)
        assert quilt not in row and karaoke not in row and spin not in row
    finally:
        _cleanup(eids)


def test_week_view_renders_day_list() -> None:
    """v4.5 PR-1: the week view is the v4 seven-day list — each day is an .ev row
    linking to that day's full lineup, under the 'This week' heading."""
    with TestClient(app) as client:
        body = client.get("/events-ui?view=week").text
    assert "This week" in body
    assert "wklist" in body
    assert re.search(r'href="/events-ui\?date=\d{4}-\d{2}-\d{2}"', body)


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


def test_youth_classes_stay_in_fitness_single_group():
    """No Kids & Family overlay (Casey 2026-06-26): a youth BMX race AND a youth
    dance class both land ONCE in Fitness & Sports (peeled into their Youth sub at
    render), never duplicated into a separate group."""
    from app.home.events_views import _occurrence_group_keys

    bmx = _occurrence_group_keys(
        "classes", title="BMX Local Race", venue=None, activity=None, is_senior=False,
    )
    assert bmx == ["classes"]
    dance = _occurrence_group_keys(
        "classes", title="Tiny Toes Ballet", venue=None, activity="Dance", is_senior=False,
    )
    assert dance == ["classes"]


def test_fitness_group_label_is_sports():
    from app.home.event_buckets import GROUP_DEFS

    labels = {k: label for k, label, _icon in GROUP_DEFS}
    assert labels["classes"] == "Fitness & Sports"


def test_events_ui_wears_v4_shell_and_has_no_emoji() -> None:
    """v4.5 PR-1: /events-ui is in the v4 language — the cond-tile strip + the v4
    stylesheet, and the For-kids narrow is a monoline places pill, not the emoji."""
    with TestClient(app) as client:
        body = client.get("/events-ui").text
    assert "/static/styles/lake_redesign.css" in body
    assert 'class="cond"' in body  # the v4 conditions strip
    assert 'class="cpill places' in body and "For Kids" in body
    # Zero emoji codepoints on the page.
    assert not any(
        0x1F000 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF for ch in body
    )


# --- (d) Month grid: weekday alignment (B-02) + one-off-only counts ----------


def test_month_grid_first_of_month_in_correct_weekday_column() -> None:
    """B-02 regression: July 1, 2099 is a Wednesday, so the Sunday-anchored
    grid must lead with exactly three blank cells (Sun/Mon/Tue) before it."""
    assert date(2099, 7, 1).weekday() == 2  # sanity: Wednesday (Mon=0)
    with TestClient(app) as client:
        body = client.get("/events-ui?view=month&cal=2099-07").text
    assert "July 2099" in body
    # Day 1 renders with this cell label regardless of whether it carries events
    # (an empty in-month day is a bare cell; a populated one is a "cell has" link).
    head = body[: body.index('<span class="dnum">1</span>')]
    # Out-of-month lead cells are the aria-hidden blanks; exactly three precede
    # a Wednesday-first month on a Sunday-anchored grid.
    assert head.count("cell empty") == 3
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
        assert ">1 event<" in cell
        assert 'class="more cls"' in cell
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
        assert "Saturday, July 25" in body  # the single-day H1
        assert 'data-k="events"' in body and title in body
        assert 'class="evnav"' in body
        assert "/events-ui?date=2099-07-24" in body  # prev day
        assert "/events-ui?date=2099-07-26" in body  # next day
        assert '<a class="today" href="/events-ui">Today</a>' in body  # back to today
    finally:
        _cleanup(eids)


# --- (g) Time TBD rows render honestly and sort last --------------------------


def test_time_tbd_rows_render_blank_and_sort_last() -> None:
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
        i_events = body.index('data-k="events"')
        block = body[i_events : body.index("</details>", i_events)]
        # Time-unknown rows show NO time, not a "Time TBD" badge (Casey 2026-06-29)
        # and never a fabricated 12 AM.
        assert "Time TBD" not in block
        assert "12 AM" not in block
        assert "10 AM" in block  # the timed sibling keeps its real time
        # TBD rows sort after timed rows within their group.
        assert block.index(tbd) > block.index(timed)
    finally:
        _cleanup(eids)
