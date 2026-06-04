"""WP-4: canonical-URL identity + recurring-series instance dedupe (M-12/M-13/M-14).

Pure-core tests for the dedup primitives (no DB) plus the cross-source dedupe
script's pairing core, including the named case: the same Facebook event id
surfaced from two sources collapses to one.
"""

from __future__ import annotations

from datetime import date

from app.events.dedup import (
    canonical_event_identity,
    recurring_series_key,
)


# --------------------------------------------------------------------------- #
# canonical_event_identity.
# --------------------------------------------------------------------------- #
def test_facebook_event_id_is_canonical_key() -> None:
    a = canonical_event_identity("https://www.facebook.com/events/1234567890/")
    b = canonical_event_identity("https://m.facebook.com/events/1234567890?ref=share")
    assert a == "fb:1234567890"
    assert a == b


def test_same_fb_event_from_two_sources_collapses() -> None:
    # go_lake_havasu organizer link vs river_scene_import "Facebook" label.
    go_lake = "https://www.facebook.com/events/55501?fbclid=ABC&utm_source=glh"
    river_scene = "facebook.com/events/55501/"
    assert canonical_event_identity(go_lake) == canonical_event_identity(river_scene)
    assert canonical_event_identity(go_lake) == "fb:55501"


def test_organizer_url_canonicalized_ignores_tracking_and_www() -> None:
    a = canonical_event_identity("https://www.Example.com/events/jazz-night/?utm_medium=x")
    b = canonical_event_identity("http://example.com/events/jazz-night")
    assert a == b
    assert a == "url:example.com/events/jazz-night"


def test_distinct_urls_distinct_keys() -> None:
    a = canonical_event_identity("https://example.com/events/a")
    b = canonical_event_identity("https://example.com/events/b")
    assert a != b


def test_canonical_identity_none_for_empty() -> None:
    assert canonical_event_identity(None) is None
    assert canonical_event_identity("") is None
    assert canonical_event_identity("   ") is None


# --------------------------------------------------------------------------- #
# recurring_series_key.
# --------------------------------------------------------------------------- #
def test_recurring_series_key_normalizes() -> None:
    k = recurring_series_key("Visitor Center!", "Farmers Market", 5)
    assert k == ("visitor center", "farmers market", 5)


def test_recurring_series_key_none_when_incomplete() -> None:
    assert recurring_series_key("", "Farmers Market", 5) is None
    assert recurring_series_key("Venue", "", 5) is None
    assert recurring_series_key("Venue", "Market", None) is None


# --------------------------------------------------------------------------- #
# Cross-source dedupe script pairing core (DB-free).
# --------------------------------------------------------------------------- #
def _lite(**kw):
    from scripts.dedupe_events_cross_source import EventLite

    base = dict(
        id="",
        title="",
        normalized_title=None,
        source="river_scene",
        date=date(2026, 6, 6),
        location_name=None,
        event_url=None,
        source_url=None,
    )
    base.update(kw)
    return EventLite(**base)


def test_find_collapses_canonical_url_keeps_higher_priority() -> None:
    from scripts.dedupe_events_cross_source import find_collapses

    rows = [
        _lite(id="rs", source="river_scene", event_url="facebook.com/events/9001/"),
        _lite(
            id="glh",
            source="go_lake_havasu",
            event_url="https://facebook.com/events/9001?fbclid=z",
        ),
    ]
    collapses = find_collapses(rows)
    assert len(collapses) == 1
    c = collapses[0]
    assert c.reason == "canonical_url"
    # go_lake_havasu (priority 1) outranks river_scene (priority 4) -> it is kept.
    assert c.keep_id == "glh"
    assert c.dup_id == "rs"
    assert "go_lake_havasu" in c.combined_source
    assert "river_scene" in c.combined_source


def test_find_collapses_recurring_series_same_day() -> None:
    from scripts.dedupe_events_cross_source import find_collapses

    rows = [
        _lite(id="a", source="go_lake_havasu", title="Farmers Market", location_name="Visitor Center"),
        _lite(id="b", source="river_scene", title="Farmers Market!", location_name="Visitor Center"),
    ]
    collapses = find_collapses(rows)
    assert len(collapses) == 1
    assert collapses[0].reason == "recurring_series"
    assert collapses[0].keep_id == "a"  # go_lake_havasu wins
    assert collapses[0].dup_id == "b"


def test_find_collapses_distinct_weeks_not_collapsed() -> None:
    from scripts.dedupe_events_cross_source import find_collapses

    rows = [
        _lite(id="w1", title="Farmers Market", location_name="Visitor Center", date=date(2026, 6, 6)),
        _lite(id="w2", title="Farmers Market", location_name="Visitor Center", date=date(2026, 6, 13)),
    ]
    # Different calendar dates -> distinct occurrences, not collapsed.
    assert find_collapses(rows) == []


def test_find_collapses_each_dup_collapsed_once() -> None:
    from scripts.dedupe_events_cross_source import find_collapses

    # One canonical-URL pair AND a same-series same-day overlap on the same dup;
    # the dup must be collapsed exactly once (canonical wins, dedup not double).
    rows = [
        _lite(id="keep", source="go_lake_havasu", title="Market", location_name="Center",
              event_url="facebook.com/events/7/"),
        _lite(id="dup", source="river_scene", title="Market", location_name="Center",
              event_url="https://facebook.com/events/7"),
    ]
    collapses = find_collapses(rows)
    dup_ids = [c.dup_id for c in collapses]
    assert dup_ids.count("dup") == 1


def test_find_collapses_shared_venue_url_is_not_identity() -> None:
    """Prod regression (2026-06-04 activation audit): 170 distinct pool classes,
    36 farmers-market dates, and different theatre shows all share one venue/
    schedule URL. A shared canonical URL alone must NOT collapse events --
    identity requires the same date AND normalized title too."""
    from scripts.dedupe_events_cross_source import find_collapses

    url = "https://lhcaz.gov/parks-recreation/open-swim-schedule"
    rows = [
        # Same URL, same date, DIFFERENT classes -> keep both.
        _lite(id="lap", title="Lap Swim", event_url=url),
        _lite(id="yoga", title="Warm Water Yoga", event_url=url),
        # Same URL, same title, DIFFERENT date -> keep both.
        _lite(id="lap2", title="Lap Swim", date=date(2026, 6, 7), event_url=url),
        # Same URL + date + title -> true dupe, collapse.
        _lite(id="lap-dup", title="Lap Swim", source="go_lake_havasu", event_url=url),
    ]
    out = find_collapses(rows)
    assert len(out) == 1
    assert {out[0].keep_id, out[0].dup_id} == {"lap", "lap-dup"}


def test_events_status_constraint_allows_duplicate() -> None:
    """The apply pass writes status='duplicate'; the migrated schema must accept
    it (prod regression 2026-06-04: ck_events_status predated the script and
    rejected the value, so --apply could never run)."""
    import uuid
    from datetime import date as _date

    from app.db.database import SessionLocal
    from app.db.models import Event

    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        from datetime import time as _time

        ev = Event(
            title=f"Dup Status Probe {suf}",
            normalized_title=f"dup status probe {suf}",
            date=_date(2026, 6, 6),
            start_time=_time(18, 0),
            location_name="Test Venue",
            location_normalized="test venue",
            description="constraint probe",
            status="duplicate",
            source="test-dedupe",
        )
        db.add(ev)
        db.commit()
        try:
            assert db.get(Event, ev.id).status == "duplicate"
        finally:
            row = db.get(Event, ev.id)
            if row is not None:
                db.delete(row)
            db.commit()
