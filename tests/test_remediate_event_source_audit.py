"""Pure-logic tests for the 2026-07-13 audit remediation (no DB writes).

Builds in-memory Event rows in the exact known-bad state each fix targets and
asserts (a) the guard fires + the planned diff is correct, and (b) the guard is
idempotent — it does NOT fire once the row is already corrected.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.models import Event
from scripts.remediate_event_source_audit_2026_07_13 import FIXES, _diff

_BY_ID = {f.event_id: f for f in FIXES}


def _ev(**kw) -> Event:
    base = dict(
        title="x", normalized_title="x", date=date(2026, 1, 1),
        start_time=time(10, 0), location_name="Somewhere",
        location_normalized="somewhere", description="d", status="live", source="s",
    )
    base.update(kw)
    return Event(**base)


def test_all_fix_ids_unique() -> None:
    assert len(_BY_ID) == len(FIXES)


def test_cirque_redate() -> None:
    f = _BY_ID["fad143e1-bb8d-4a6c-8950-3691efc833b7"]
    ev = _ev(title="Cirque de Masquerade Charity Gala", date=date(2026, 9, 12))
    assert f.guard(ev)
    assert _diff(ev, f.change(ev)) == {"date": (date(2026, 9, 12), date(2026, 9, 11))}
    # idempotent: already 09-11 -> guard off
    assert not f.guard(_ev(title="Cirque de Masquerade Charity Gala", date=date(2026, 9, 11)))


def test_london_bridge_repoint() -> None:
    f = _BY_ID["99a38686-d69e-4ed4-a12f-5a4c1fe7c66c"]
    ev = _ev(
        title="London Bridge Days Parade",
        event_url="https://londonbridgedays.com/parade/",
        source_url="https://londonbridgedays.com/parade/",
    )
    assert f.guard(ev)
    diff = _diff(ev, f.change(ev))
    assert diff["event_url"][1] == "https://londonbridgedays.com/"
    assert diff["source_url"][1] == "https://londonbridgedays.com/"
    # idempotent: already repointed
    assert not f.guard(_ev(title="London Bridge Days Parade",
                           event_url="https://londonbridgedays.com/", source_url=None))


def test_crosscutt_retire_dup() -> None:
    f = _BY_ID["66ad5275-9c79-4713-a416-b468eb8758d3"]
    ev = _ev(title="Crosscutt at The Flying X Saloon", date=date(2026, 7, 31),
             location_name="Flying X Saloon")
    assert f.guard(ev)
    assert _diff(ev, f.change(ev)) == {"status": ("live", "deleted")}
    assert not f.guard(_ev(title="Crosscutt", date=date(2026, 7, 31), status="deleted"))


@pytest.mark.parametrize(
    "eid,title,venue",
    [
        ("c26f0760-45f9-49ac-8a9d-216607509360", "Yoga Nidra & Sound Bath", "Llamaste Yoga and Healing"),
        ("aafdf8f4-f0c2-4868-8a99-218b95a282ea", "Water Ballon War", "Rotary Park"),
        ("78849908-5a31-4e38-a6f6-8bcf68e5211b", "Girls Night In", "Southside District"),
        ("d113e223-fab7-416b-9485-cfaabbbf5048", "LHHS Class of 2016's 10 Year Reunion", "Mudshark Brewery and Public House"),
    ],
)
def test_venue_fixes(eid: str, title: str, venue: str) -> None:
    f = _BY_ID[eid]
    ev = _ev(title=title, location_name="Lake Havasu", location_normalized="lake havasu")
    assert f.guard(ev)
    diff = _diff(ev, f.change(ev))
    assert diff["location_name"][1] == venue
    assert diff["location_normalized"][1] == venue.lower().strip()
    # idempotent: a non-generic venue is left alone
    assert not f.guard(_ev(title=title, location_name=venue, location_normalized=venue.lower()))


def test_shoreline_time_fix() -> None:
    f = _BY_ID["741b4a89-06ca-429e-b6c3-f51984560988"]
    ev = _ev(title="Shoreline to Skyline UTV Adventure", start_time=time(0, 0))
    assert f.guard(ev)
    assert _diff(ev, f.change(ev)) == {"start_time": (time(0, 0), time(18, 0))}
    assert not f.guard(_ev(title="Shoreline to Skyline UTV Adventure", start_time=time(18, 0)))
