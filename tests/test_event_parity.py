"""PR E tests: event-category stamping, recurrence-flag fix, AZ-time drop."""

from __future__ import annotations

from datetime import date, time
from uuid import uuid4

import pytest

from app.contrib.source_category_map import derive_event_category
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.recurrence import (
    _event_is_recurring,
    expand_event,
    normalize_recurrence_flag,
)

_MODULE_SEED = "_MODULE_SEED_SOURCE"


# ---------------------------------------------------------------------------
# derive_event_category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tags,expected",
    [
        (["music", "bands"], "music"),
        (["boat-show"], "boating-and-lake"),
        (["uncategorized"], "misc"),
        (["uncategorized", "fundraiser"], "fundraiser-and-charity"),  # specific beats misc
        (["totally-unknown-tag"], None),
        ([], None),
        (None, None),
    ],
)
def test_derive_event_category(tags: list[str] | None, expected: str | None) -> None:
    assert derive_event_category(tags) == expected


# ---------------------------------------------------------------------------
# recurrence flag fix
# ---------------------------------------------------------------------------


def test_normalize_recurrence_flag() -> None:
    # flag with no data -> False
    assert normalize_recurrence_flag(is_recurring=True, rrule=None, rdate=None) is False
    # flag with rrule -> True
    assert normalize_recurrence_flag(is_recurring=True, rrule="FREQ=WEEKLY", rdate=None) is True
    # flag with rdate -> True
    assert normalize_recurrence_flag(is_recurring=True, rrule=None, rdate=["2026-07-04"]) is True
    # no flag -> False regardless
    assert normalize_recurrence_flag(is_recurring=False, rrule="FREQ=WEEKLY", rdate=None) is False


def test_recurring_flag_without_data_renders_on_stored_date() -> None:
    """The 266-row bug: is_recurring=True but no rrule/rdate must NOT vanish."""
    ev = Event(
        title="Stray Recurring",
        normalized_title="stray recurring",
        date=date(2026, 7, 15),
        start_time=time(10, 0),
        location_name="Rotary Park",
        location_normalized="rotary park",
        description="x",
        entity_id="dummy",
        is_recurring=True,
        rrule=None,
        rdate=None,
    )
    # not treated as recurring (no data) ...
    assert _event_is_recurring(ev) is False
    # ... so it renders on its single stored date instead of expanding to nothing
    occ = expand_event(ev, window_start=date(2026, 7, 1), window_end=date(2026, 7, 31))
    assert occ == [date(2026, 7, 15)]


def test_genuine_rrule_still_expands() -> None:
    ev = Event(
        title="Weekly Yoga",
        normalized_title="weekly yoga",
        date=date(2026, 7, 6),  # a Monday
        start_time=time(9, 0),
        location_name="Studio",
        location_normalized="studio",
        description="x",
        entity_id="dummy",
        is_recurring=True,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        rdate=None,
    )
    occ = expand_event(ev, window_start=date(2026, 7, 1), window_end=date(2026, 7, 31))
    assert date(2026, 7, 6) in occ and date(2026, 7, 13) in occ and len(occ) >= 4


# ---------------------------------------------------------------------------
# Event.category persists (integration)
# ---------------------------------------------------------------------------


def test_event_category_column_persists() -> None:
    with SessionLocal() as db:
        ent = Entity(
            entity_type="event",
            slug=f"parity-evt-{uuid4().hex[:10]}",
            name="Parity Event",
            source=_MODULE_SEED,
        )
        db.add(ent)
        db.flush()
        ev = Event(
            title="Parity Event",
            normalized_title="parity event",
            date=date(2026, 8, 1),
            start_time=time(12, 0),
            location_name="Rotary Park",
            location_normalized="rotary park",
            description="x",
            entity_id=ent.id,
            category=derive_event_category(["music"]),
            source=_MODULE_SEED,
        )
        db.add(ev)
        db.commit()
        got = db.get(Event, ev.id)
        assert got is not None and got.category == "music"
        db.delete(got)
        db.delete(db.get(Entity, ent.id))
        db.commit()
