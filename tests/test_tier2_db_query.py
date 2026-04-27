"""Tests for ``app.chat.tier2_db_query``."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.chat import tier2_db_query
from app.chat.tier2_db_query import query as tier2_query
from app.chat.tier2_schema import Tier2Filters
from app.contrib.hours_helper import LAKE_HAVASU_TZ
from app.db.models import Event, Program, Provider


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _prov(db: Session, *, name: str, category: str = "misc", address: str | None = None) -> Provider:
    p = Provider(
        provider_name=name,
        category=category,
        verified=True,
        draft=False,
        is_active=True,
        source="tier2-test",
        address=address,
        description=f"{name} description for search",
    )
    db.add(p)
    db.flush()
    return p


def _prog(
    db: Session,
    *,
    title: str,
    provider: Provider,
    activity_category: str = "general",
    age_min: int | None = None,
    age_max: int | None = None,
    schedule_days: list[str] | None = None,
    location_name: str = "Main St",
    location_address: str | None = None,
) -> Program:
    pr = Program(
        title=title,
        description=f"{title} program description",
        activity_category=activity_category,
        age_min=age_min,
        age_max=age_max,
        schedule_days=list(schedule_days or ["monday"]),
        schedule_start_time="09:00",
        schedule_end_time="17:00",
        location_name=location_name,
        location_address=location_address,
        provider_name=provider.provider_name,
        provider_id=provider.id,
        source="tier2-test",
        verified=True,
        is_active=True,
        draft=False,
    )
    db.add(pr)
    db.flush()
    return pr


def _evt(
    db: Session,
    *,
    title: str,
    on_date: date,
    end_date: date | None = None,
    location_name: str = "Downtown",
    tags: list[str] | None = None,
    provider: Provider | None = None,
    is_recurring: bool = False,
    start: time = time(10, 0),
) -> Event:
    loc_norm = location_name.lower().strip()
    e = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        end_date=end_date,
        start_time=start,
        end_time=None,
        location_name=location_name,
        location_normalized=loc_norm,
        description=f"{title} event description",
        event_url="https://example.com/e",
        tags=list(tags or []),
        status="live",
        source="tier2-test",
        verified=True,
        provider_id=provider.id if provider else None,
        is_recurring=is_recurring,
    )
    db.add(e)
    db.flush()
    return e


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_entity_name_exact_match(db: Session) -> None:
    suf = _suffix()
    p = _prov(db, name=f"Bridge City Combat {suf}")
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, entity_name=f"Bridge City Combat {suf}"))
    types = {r["type"] for r in rows}
    assert "provider" in types
    assert any("Bridge City" in r["name"] for r in rows)


def test_entity_name_partial_case_insensitive(db: Session) -> None:
    suf = _suffix()
    p = _prov(db, name=f"Altitude Trampoline Park {suf}")
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, entity_name="altitude"))
    assert any("Altitude" in r["name"] and suf in r["name"] for r in rows)


def test_category_bmx_mapping(db: Session) -> None:
    suf = _suffix()
    pv = _prov(db, name=f"Venue {suf}", category="recreation")
    _prog(db, title=f"BMX racing intro {suf}", provider=pv, activity_category="bmx")
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, category="bmx"))
    assert any(r["type"] == "program" and suf in r["name"] for r in rows)


def test_age_min_includes_six(db: Session) -> None:
    suf = _suffix()
    pv = _prov(db, name=f"Kids Gym {suf}")
    _prog(db, title=f"Tumble class {suf}", provider=pv, age_min=5, age_max=10)
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, age_min=6, age_max=6))
    assert any(r["type"] == "program" and "Tumble" in r["name"] for r in rows)


def test_location_sara_park(db: Session) -> None:
    suf = _suffix()
    pv = _prov(db, name=f"Park Org {suf}")
    _prog(
        db,
        title=f"Outdoor yoga {suf}",
        provider=pv,
        location_name="Sara Park Field",
        location_address="Sara Park Rd",
    )
    _evt(db, title=f"Concert {suf}", on_date=date(2030, 7, 1), location_name="Sara Park Amphitheater")
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, location="Sara Park"))
    assert len(rows) >= 1
    loc_blob = lambda r: (r.get("location_name") or "") + (r.get("location") or "")
    assert any("Sara" in loc_blob(r) for r in rows)


def test_day_of_week_saturday_event(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 6, 8))
    suf = _suffix()
    pv = _prov(db, name=f"E Org {suf}")
    sat = date(2026, 6, 13)
    _evt(db, title=f"Saturday fair {suf}", on_date=sat, provider=pv)
    db.commit()
    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, day_of_week=["saturday"])
    )
    assert any(r["type"] == "event" and suf in r["name"] for r in rows)


def test_day_of_week_weekend_program(db: Session) -> None:
    suf = _suffix()
    pv = _prov(db, name=f"Weekend Org {suf}")
    _prog(
        db,
        title=f"Weekend camp {suf}",
        provider=pv,
        schedule_days=["saturday", "sunday"],
    )
    db.commit()
    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, day_of_week=["saturday", "sunday"])
    )
    assert any(r["type"] == "program" and suf in r["name"] for r in rows)


def test_time_window_tomorrow(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 6, 10))
    suf = _suffix()
    pv = _prov(db, name=f"T Org {suf}")
    _evt(db, title=f"Tomorrow show {suf}", on_date=date(2026, 6, 11), provider=pv)
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, time_window="tomorrow"))
    assert any(r["type"] == "event" and "Tomorrow" in r["name"] for r in rows)


def test_time_window_upcoming_chronological(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 5, 1))
    suf = _suffix()
    pv = _prov(db, name=f"U Org {suf}")
    _evt(db, title=f"Later fest {suf}", on_date=date(2026, 6, 20), provider=pv)
    _evt(db, title=f"Sooner fest {suf}", on_date=date(2026, 6, 5), provider=pv)
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, time_window="upcoming"))
    ev_rows = [r for r in rows if r["type"] == "event" and suf in r["name"]]
    assert len(ev_rows) >= 2
    dates = [r["date"] for r in ev_rows]
    assert dates == sorted(dates)


def test_time_window_this_month(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 6, 15))
    suf = _suffix()
    pv = _prov(db, name=f"M Org {suf}")
    _evt(db, title=f"June gala {suf}", on_date=date(2026, 6, 22), provider=pv)
    _evt(db, title=f"July gala {suf}", on_date=date(2026, 7, 2), provider=pv)
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, time_window="this_month"))
    assert any("June" in r["name"] for r in rows)
    assert not any("July" in r["name"] and suf in r["name"] for r in rows)


def test_empty_filters_returns_sample(db: Session) -> None:
    suf = _suffix()
    pv = _prov(db, name=f"Sample Prov {suf}")
    _prog(db, title=f"Sample Pr {suf}", provider=pv)
    _evt(db, title=f"Sample Ev {suf}", on_date=date(2031, 1, 1), provider=pv)
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.95))
    assert len(rows) >= 1
    assert len(rows) <= 8


def test_result_cap_eight(db: Session) -> None:
    suf = _suffix()
    pv = _prov(db, name=f"Cap Org {suf}")
    for i in range(12):
        _evt(
            db,
            title=f"bmxcaptest {suf} n{i}",
            on_date=date(2032, 1, i + 1),
            provider=pv,
        )
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, category="bmxcaptest"))
    assert len(rows) == 8


def test_open_now_excludes_providers_without_structured_hours(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tier2_db_query,
        "_now_lake_havasu",
        lambda: datetime(2026, 6, 15, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ),
    )
    suf = _suffix()
    p = _prov(db, name=f"ONX {suf}", category="onxcat")
    p.hours_structured = None
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, entity_name=f"ONX {suf}", open_now=True))
    assert not any(r["type"] == "provider" for r in rows)


def test_row_shape_type_and_name(db: Session) -> None:
    suf = _suffix()
    p = _prov(db, name=f"Shape Test {suf}")
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, entity_name=f"Shape Test {suf}"))
    assert rows
    r = rows[0]
    assert r["type"] in ("provider", "program", "event")
    assert "name" in r and r["name"]


def test_broad_window_dedupes_recurring_series_to_one(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """>30d: weekly ``is_recurring`` BMX (same title + start) collapses to a single event row (earliest)."""
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 5, 15))
    suf = _suffix()
    mark = f"bmxrs{suf}"
    pv = _prov(db, name=f"Rseries {suf}")
    t0 = time(18, 30)
    d0 = date(2026, 6, 2)  # Tuesday
    for i in range(12):
        d = d0 + timedelta(days=7 * i)
        _evt(
            db,
            title=f"USA {mark} wk",
            on_date=d,
            provider=pv,
            is_recurring=True,
            start=t0,
        )
    db.commit()
    rows = tier2_query(
        Tier2Filters(
            parser_confidence=0.9,
            date_start=date(2026, 6, 1),
            date_end=date(2026, 8, 31),
            category=mark,
        )
    )
    evs = [r for r in rows if r["type"] == "event" and mark in r["name"]]
    assert len(evs) == 1


def test_narrow_window_keeps_earliest_rows_without_recurring_collapse(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """≤30d: same recurring series can appear in more than one slot (legacy first-N behavior)."""
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 5, 20))
    suf = _suffix()
    mark = f"dnrow{suf}"
    pv = _prov(db, name=f"NarrowR {suf}")
    t0 = time(9, 0)
    for i in range(8):
        _evt(
            db,
            title=f"Daily{mark} row",
            on_date=date(2026, 6, 1) + timedelta(days=i),
            provider=pv,
            is_recurring=True,
            start=t0,
        )
    db.commit()
    rows = tier2_query(
        Tier2Filters(
            parser_confidence=0.9,
            date_start=date(2026, 6, 1),
            date_end=date(2026, 6, 14),
            category=mark,
        )
    )
    evs = [r for r in rows if r["type"] == "event" and mark in r["name"]]
    assert len(evs) == 8


def test_broad_window_bucketing_includes_late_dates_if_early_clustered(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """>30d + many early + few late: secondary bucketing should not take only the earliest week."""
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 4, 1))
    suf = _suffix()
    mark = f"bbktm{suf}"
    pv = _prov(db, name=f"BucketF {suf}")
    n = 0
    for d in range(3):
        for _h in range(4):
            _evt(
                db,
                title=f"{mark} e{n} earlyrow",
                on_date=date(2026, 6, 1) + timedelta(days=d),
                provider=pv,
            )
            n += 1
    for j in range(4):
        _evt(
            db,
            title=f"{mark} l{j} latecol",
            on_date=date(2026, 7, 25) + timedelta(days=j),
            provider=pv,
        )
    db.commit()
    rows = tier2_query(
        Tier2Filters(
            parser_confidence=0.9,
            date_start=date(2026, 6, 1),
            date_end=date(2026, 8, 31),
            category=mark,
        )
    )
    evs = [r for r in rows if r["type"] == "event" and mark in r["name"]]
    by_date = {r["date"] for r in evs}
    assert any(d.startswith("2026-07") for d in by_date), by_date


def test_multi_day_event_surfaces_on_middle_day_date_exact(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Won Bass–style: start May 7, end May 9 → ``date_exact=May 8`` still returns the event."""
    monkeypatch.setattr(tier2_db_query, "_today", lambda: date(2026, 5, 1))
    suf = _suffix()
    mark = f"wonbassmd{suf}"
    pv = _prov(db, name=f"MultiEvOrg {suf}")
    _evt(
        db,
        title=f"{mark} Havasu Open",
        on_date=date(2026, 5, 7),
        end_date=date(2026, 5, 9),
        provider=pv,
    )
    db.commit()
    rows = tier2_query(
        Tier2Filters(
            parser_confidence=0.9,
            entity_name=mark,
            date_exact=date(2026, 5, 8),
        )
    )
    assert any(
        r["type"] == "event" and mark in r["name"] and r.get("end_date") == "2026-05-09" for r in rows
    ), rows
