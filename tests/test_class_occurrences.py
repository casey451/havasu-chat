"""Venue class Schedules surface on the calendar + events feed (read-time bridge)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from app.db.database import SessionLocal
from app.db.models import Entity, Event, Provider, Schedule
from app.events.class_occurrences import (
    ClassOccurrence,
    class_occurrences_in_window,
    drop_event_duplicates,
    program_anchor,
)
from app.home import events_views, sandstone
from app.home.today_feed import today_feed


def _node_rows(node: dict) -> list[dict]:
    """Rows of a subgroup node plus all nested ``children`` (the youth/discipline
    third level — Phase 1), matching the recursive template render."""
    rows: list[dict] = list(node.get("rows") or [])
    for child in node.get("children") or []:
        rows += _node_rows(child)
    return rows


def _all_rows(groups: list[dict]) -> list[dict]:
    """Flatten a day_groups result to the rows the template actually renders: a
    group's subgroup rows (recursing nested children) when it is split, else its
    flat rows (the two overlap — subgroups are a split OF ``rows`` — so we never
    count both, matching the ``{% if g.subgroups %}...{% else %}...{% endif %}``
    render)."""
    rows: list[dict] = []
    for g in groups:
        subs = g.get("subgroups") or []
        if subs:
            for sub in subs:
                rows += _node_rows(sub)
        else:
            rows += g.get("rows") or []
    return rows


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_venue_with_class(title: str, days: list[str]) -> tuple[str, str, str]:
    """Provider (+entity) with one recurring class. Returns (slug, entity_id, name)."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Calendar Combat {suf}", category="fitness_sports",
            verified=True, draft=False, is_active=True, pending_review=False,
            source="test-class-occurrences",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        db.add(
            Schedule(
                entity_id=eid, schedule_type="recurring", days_of_week=days,
                start_time=time(18, 0), end_time=time(19, 0), notes=title,
                created_at=_now(), updated_at=_now(),
            )
        )
        db.commit()
        return p.slug, eid, p.provider_name


def _make_permalinkless_program(title: str, days: list[str]) -> str:
    """Active venue Entity + recurring Schedule but NO Provider — a program with
    no permalink (occ.url == ""), like "Havasu Horseback Rides". Returns the
    venue name."""
    suf = uuid.uuid4().hex[:8]
    name = f"Havasu Horseback Rides {suf}"
    with SessionLocal() as db:
        ent = Entity(
            entity_type="venue", slug=f"venue-{suf}", name=name,
            source="test-class-occurrences", is_active=True,
        )
        db.add(ent)
        db.commit()
        db.add(
            Schedule(
                entity_id=ent.id, schedule_type="recurring", days_of_week=days,
                start_time=time(10, 0), end_time=time(11, 0), notes=title,
                created_at=_now(), updated_at=_now(),
            )
        )
        db.commit()
    return name


def test_expansion_hits_every_matching_weekday() -> None:
    title = f"BJJ Fundamentals {uuid.uuid4().hex[:6]}"
    slug, _eid, name = _make_venue_with_class(title, ["monday", "tuesday", "wednesday", "thursday"])
    with SessionLocal() as db:
        occs = [
            o for o in class_occurrences_in_window(
                db, window_start=date(2026, 12, 1), window_end=date(2026, 12, 31)
            )
            if o.title == title
        ]
    # December 2026: Mon-Thu occur 4-5 times each; 4 weekdays -> 19 occurrences.
    assert len(occs) == 19
    assert {o.date.weekday() for o in occs} == {0, 1, 2, 3}
    assert all(o.provider_slug == slug for o in occs)
    assert occs[0].url == f"/provider/{slug}"


def test_event_duplicates_dropped_by_title_and_date() -> None:
    title = f"Lap Swim Clone {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["friday"])
    with SessionLocal() as db:
        occs = [
            o for o in class_occurrences_in_window(
                db, window_start=date(2026, 12, 4), window_end=date(2026, 12, 11)
            )
            if o.title == title
        ]
    assert len(occs) == 2  # Fri Dec 4 + Fri Dec 11
    kept = drop_event_duplicates(occs, {(title.lower(), date(2026, 12, 4))})
    assert [o.date for o in kept] == [date(2026, 12, 11)]


def test_month_calendar_shows_schedule_classes() -> None:
    title = f"Calendar Karate {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["tuesday"])
    with SessionLocal() as db:
        cal = sandstone.calendar_month(db, year=2026, month=12, today=date(2026, 12, 1))
    cells = [c for week in cal["weeks"] for c in week]
    tuesdays = [
        c for c in cells
        if c.get("in_month") and date.fromisoformat(c["iso"]).weekday() == 1
    ]
    assert tuesdays, "December 2026 has Tuesdays"
    for cell in tuesdays:
        # Schedule classes are recurring: they land in the collapsed class
        # badge (class_count), never in the one-off pill slots / count.
        assert cell["class_count"] >= 1


def test_events_ui_day_page_lists_class_with_venue_link() -> None:
    # Two-surface split (spec §1): venue Schedule classes are Places & Ongoing
    # content, not Calendar happenings. The row the Places surface renders (built
    # by day_groups' mixed mode; Phase 3 surfaces it on the Places tab) carries
    # the provider link.
    title = f"Day Page Judo {uuid.uuid4().hex[:6]}"
    slug, _eid, _name = _make_venue_with_class(title, ["wednesday"])
    with SessionLocal() as db:
        groups = events_views.day_groups(db, day=date(2026, 12, 9), events_only=False)
    row = next((r for r in _all_rows(groups) if title in (r.get("title") or "")), None)
    assert row is not None
    assert row["url"] == f"/provider/{slug}"


def test_events_ui_skips_class_that_is_also_an_event() -> None:
    """Aquatic-style duplicates (class exists as a recurring Event too) show once
    on the Places-bound class list (drop_event_duplicates, mixed mode)."""
    title = f"Dup Aqua Fit {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["thursday"])
    with SessionLocal() as db:
        db.add(
            Event(
                title=title, normalized_title=title.lower(),
                date=date(2026, 12, 10), start_time=time(18, 0),
                location_name="Aquatic Center", location_normalized="aquatic center",
                description="The event-table twin of the schedule row.",
                source="parks_rec", tags=["class"], status="live",
            )
        )
        db.commit()
    with SessionLocal() as db:
        groups = events_views.day_groups(db, day=date(2026, 12, 10), events_only=False)
    assert sum(1 for r in _all_rows(groups) if (r.get("title") or "") == title) == 1


def test_program_anchor_is_deterministic_and_slugged() -> None:
    """The deep-link anchor is a stable slug from title+venue, so the home-feed
    link and the /events-ui row id always agree (Item 2)."""
    a = program_anchor("Pony / Lead Line Rides", "Havasu Horseback Rides")
    assert a == "program-pony-lead-line-rides-havasu-horseback-rides"
    # Deterministic: same inputs -> same anchor.
    assert program_anchor("Pony / Lead Line Rides", "Havasu Horseback Rides") == a
    # ClassOccurrence exposes the same value via its .anchor property.
    occ = ClassOccurrence(
        title="Pony / Lead Line Rides", date=date(2026, 12, 5),
        start_time=time(10, 0), end_time=time(11, 0),
        venue="Havasu Horseback Rides", provider_slug=None, weekdays=frozenset({5}),
    )
    assert occ.anchor == a


def test_url_prefers_slug_then_website_then_empty() -> None:
    """The row link resolves to the directory page first, the provider website
    next, and an honest empty string when neither exists (brief 2026-06-23:
    "if none exists, the provider's website/source")."""
    base = dict(
        title="Reformer Pilates", date=date(2026, 12, 5),
        start_time=time(9, 0), end_time=time(10, 0),
        venue="Havasu Pilates Studio", weekdays=frozenset({4}),
    )
    # 1) directory slug wins.
    occ = ClassOccurrence(provider_slug="havasu-pilates-studio",
                          provider_website="https://example.com/", **base)
    assert occ.url == "/provider/havasu-pilates-studio"
    # 2) no slug -> fall back to the provider website.
    occ = ClassOccurrence(provider_slug=None,
                          provider_website="https://havasupilates.example/", **base)
    assert occ.url == "https://havasupilates.example/"
    # 3) neither -> honest non-link row.
    occ = ClassOccurrence(provider_slug=None, provider_website=None, **base)
    assert occ.url == ""


def test_pageless_venue_links_to_curated_website(monkeypatch) -> None:
    """A page-less class venue (no Provider) with a known real website links to
    that site (Casey 2026-06-23: link a legit business instead of hiding it).
    Monkeypatched so the test doesn't depend on a prod entity slug."""
    from app.events import class_occurrences as co

    suf = uuid.uuid4().hex[:8]
    slug = f"venue-{suf}"
    title = f"Reformer Pilates {suf}"
    with SessionLocal() as db:
        ent = Entity(
            entity_type="venue", slug=slug, name=f"Havasu Pilates Studio {suf}",
            source="test-class-occurrences", is_active=True,
        )
        db.add(ent)
        db.commit()
        eid = ent.id
        db.add(Schedule(
            entity_id=eid, schedule_type="recurring", days_of_week=["monday"],
            start_time=time(9, 0), end_time=time(10, 0), notes=title,
            created_at=_now(), updated_at=_now(),
        ))
        db.commit()
    monkeypatch.setitem(co._PAGELESS_VENUE_WEBSITES, slug, "https://havasupilates.example/")
    try:
        with SessionLocal() as db:
            occs = [o for o in co.class_occurrences_in_window(
                db, window_start=date(2026, 12, 1), window_end=date(2026, 12, 31)
            ) if o.title == title]
        assert occs, "seeded page-less class not found"
        assert occs[0].provider_slug is None
        assert occs[0].url == "https://havasupilates.example/"
    finally:
        with SessionLocal() as db:
            db.query(Schedule).filter(Schedule.entity_id == eid).delete()
            db.query(Entity).filter(Entity.id == eid).delete()
            db.commit()


def test_schedule_twins_collapse_exact_slot_title_variants() -> None:
    """An over-captured venue stored one class 4-5x per slot under title variants
    ("11:00 AM Beginner Pilates", "11:00 AM Pilates", "Reformer Pilates - 11:00
    AM Mon/Wed/Fri"). Same exact slot (start+end+weekdays) + a shared activity
    word collapses to one (Havasu Pilates filled a whole Pilates wall on live)."""
    from app.events.class_occurrences import ClassOccurrence, _drop_schedule_twins

    d = date(2026, 12, 7)
    wd = frozenset({0, 2, 4})

    def occ(title: str) -> ClassOccurrence:
        return ClassOccurrence(
            title=title, date=d, start_time=time(11, 0), end_time=time(11, 50),
            venue="Havasu Pilates Studio", provider_slug=None, weekdays=wd,
        )

    rows = [
        occ("11:00 AM Beginner Pilates (Mon/Wed/Fri)"),
        occ("11:00 AM Pilates"),
        occ("11:00 AM Reformer Pilates (Mon, Wed & Fri)"),
        occ("Reformer Pilates - 11:00 AM Mon/Wed/Fri"),
    ]
    kept = _drop_schedule_twins(rows)
    assert len(kept) == 1, [k.title for k in kept]


def test_schedule_twins_keep_distinct_same_slot_classes() -> None:
    """Two genuinely DIFFERENT classes at the same slot (no shared activity word
    — a two-room venue running Yoga and Spin at 6 PM) are NOT merged."""
    from app.events.class_occurrences import ClassOccurrence, _drop_schedule_twins

    d = date(2026, 12, 7)
    wd = frozenset({0})

    def occ(title: str) -> ClassOccurrence:
        return ClassOccurrence(
            title=title, date=d, start_time=time(18, 0), end_time=time(19, 0),
            venue="Big Multi-Room Gym", provider_slug=None, weekdays=wd,
        )

    kept = _drop_schedule_twins([occ("Yoga"), occ("Spin")])
    assert len(kept) == 2, [k.title for k in kept]


def test_home_feed_permalinkless_program_has_no_fake_details_link() -> None:
    """A permalink-less program (no provider page) still appears in the home
    feed, but renders WITHOUT a "Details →" link — we no longer fabricate a
    self-referential ``/events-ui?date=…#program-…`` anchor that just points back
    at the same bare row (no real source)."""
    title = f"Pony Lead Line Rides {uuid.uuid4().hex[:6]}"
    venue = _make_permalinkless_program(title, ["saturday"])
    day = date(2026, 12, 5)  # a Saturday
    with SessionLocal() as db:
        feed = today_feed(db, day=day)
    rows = []
    for g in feed["groups"]:
        if g["key"] == "movies":
            continue
        rows.extend(g.get("rows") or [])
        for sub in g.get("subgroups") or []:
            rows.extend(sub.get("rows") or [])
    row = next((r for r in rows if r.get("venue") == venue), None)
    assert row is not None, "permalink-less program should still appear in the feed"
    assert not row.get("url"), "should render without a fabricated Details link"
    assert "#program" not in (row.get("url") or "")


def test_events_ui_renders_program_anchor_id() -> None:
    """The permalink-less program's Places row carries the matching deep-link
    anchor so the home-feed link lands on it (Item 2; Places-bound under the
    two-surface split)."""
    title = f"Pony Lead Line Rides {uuid.uuid4().hex[:6]}"
    venue = _make_permalinkless_program(title, ["wednesday"])
    anchor = program_anchor(title, venue)
    with SessionLocal() as db:
        groups = events_views.day_groups(db, day=date(2026, 12, 9), events_only=False)
    row = next((r for r in _all_rows(groups) if title in (r.get("title") or "")), None)
    assert row is not None
    assert row.get("anchor") == anchor


def test_class_cards_survive_busy_day_cap() -> None:
    """The per-window cap must not silently drop class series on busy days
    (prod: 12+ one-off events filled the 16-card cap before any class)."""
    title = f"Cap Survivor Aikido {uuid.uuid4().hex[:6]}"
    _make_venue_with_class(title, ["saturday"])
    with SessionLocal() as db:
        for i in range(20):
            db.add(
                Event(
                    title=f"Busy Day Filler {i} {uuid.uuid4().hex[:4]}",
                    normalized_title=f"busy day filler {i}",
                    date=date(2026, 12, 12), start_time=time(10, 0),
                    location_name="Main St", location_normalized="main st",
                    description="One-off filler event to saturate the window cap.",
                    source="admin", tags=["community"], status="live",
                )
            )
        db.commit()
    with SessionLocal() as db:
        groups = events_views.day_groups(db, day=date(2026, 12, 12), events_only=False)
    assert any(title in (r.get("title") or "") for r in _all_rows(groups))
