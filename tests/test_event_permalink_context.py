"""Event permalink handler context: is_past banner + NULL-time formatting.

Follow-up to WP-3/WP-4: the event_permalink.html template references `is_past`
(the "This event has passed" banner) but the main.py handler never passed it,
so the banner was dead. WP-4 also allows NULL event times at ingest, which would
500 the old `_format_event_datetime` (it dereferenced start_time unconditionally).
These tests pin both fixes. The helpers read only attributes, so a lightweight
namespace stands in for an Event row -- no DB, no shared-session pollution.
"""

from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.main import (
    _event_is_past,
    _event_link_html,
    _format_event_datetime,
    _link_domain,
    _link_label,
    _venue_profile_url,
)

PHX = ZoneInfo("America/Phoenix")
# Thursday, June 4 2026, noon local -- fixed reference for deterministic cases.
REF = datetime(2026, 6, 4, 12, 0, tzinfo=PHX)


def _ev(**kw):
    base = dict(
        date=date(2026, 6, 4),
        start_time=time(10, 0),
        end_date=None,
        end_time=None,
        rdate=None,
        rrule=None,
        is_recurring=False,
        exdate=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_format_datetime_with_time():
    assert _format_event_datetime(_ev(start_time=time(10, 30))) == "Thursday, June 4, 10:30 AM"


def test_format_datetime_null_time_does_not_crash():
    # WP-4 NULL time -- date only, no fabricated time, no AttributeError.
    out = _format_event_datetime(_ev(start_time=None))
    assert out == "Thursday, June 4"


def test_is_past_one_off_yesterday_is_past():
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 3))) is True


def test_is_past_one_off_tomorrow_is_not_past():
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 5))) is False


def test_is_past_today_no_end_time_not_past_until_day_ends():
    # 1.3 fix: a same-day event with NO end_time is NOT "passed" until the local
    # day is over (the old 3-hour-run assumption flipped a morning event to
    # "passed" mid-morning). Started 8:00, now noon -> still today, NOT past.
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=time(8, 0))) is False


def test_is_past_morning_event_not_past_minutes_after_start():
    # 1.3 regression: the 9:00 AM Board of Adjustment meeting (no end_time) wore
    # "This event has passed" at 9:07 AM. It must NOT be considered past then.
    now_907 = datetime(2026, 6, 4, 9, 7, tzinfo=PHX)
    with patch("app.main.now_lake_havasu", return_value=now_907):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=time(9, 0))) is False


def test_is_past_no_end_time_midday_not_past():
    # Started 10:00, now noon, no end_time -> not past (rest of the day to run).
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=time(10, 0))) is False


def test_is_past_explicit_end_time_is_authoritative():
    # A real end time skips the grace window entirely.
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert (
            _event_is_past(
                _ev(date=date(2026, 6, 4), start_time=time(9, 0), end_time=time(11, 0))
            )
            is True
        )


def test_is_past_today_time_still_upcoming():
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=time(14, 0))) is False


def test_is_past_today_date_only_not_buried_midday():
    # A same-day all-day event (NULL time) is not "passed" mid-day.
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 4), start_time=None)) is False


def test_is_past_recurring_rdate_future_occurrence_not_past():
    # An rdate set with a future occurrence -> still recurring -> not "passed".
    with patch("app.main.now_lake_havasu", return_value=REF):
        assert _event_is_past(_ev(date=date(2026, 6, 3), rdate=["2026-06-09"])) is False


def test_is_past_recurring_rrule_anchor_in_past_not_past():
    # N1: a weekly series anchored at an old date (the senior rows seed at
    # 2024-01-01) is NOT "passed" while the rule still yields future dates.
    with patch("app.main.now_lake_havasu", return_value=REF):
        ev = _ev(
            date=date(2024, 1, 1),
            start_time=time(8, 30),
            rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
            is_recurring=True,
        )
        assert _event_is_past(ev) is False
        # ...and the shown date is the next occurrence, never the 2024 anchor.
        assert "January 1" not in _format_event_datetime(ev)


def test_is_past_recurring_series_ended_is_past():
    # An RRULE whose UNTIL is in the past has no future occurrence -> passed.
    with patch("app.main.now_lake_havasu", return_value=REF):
        ev = _ev(
            date=date(2024, 1, 1),
            start_time=time(9, 0),
            rrule="FREQ=WEEKLY;BYDAY=MO;UNTIL=20240301T000000",
            is_recurring=True,
        )
        assert _event_is_past(ev) is True


def test_malformed_recurrence_never_raises():
    # Persisted recurrence data is known-messy (that's what N1 is about). A bad
    # rrule / exdate / rdate must NOT raise out of _event_is_past or
    # _format_event_datetime (which would 500 the detail page) — it degrades to
    # the anchor date. A malformed-but-future-anchored series is not "passed".
    with patch("app.main.now_lake_havasu", return_value=REF):
        ev = _ev(
            date=date(2026, 12, 1),
            start_time=time(9, 0),
            rrule="RRULE:FREQ=GARBAGE;BYDAY=ZZ",
            is_recurring=True,
            exdate=["not-a-date", "2026-13-99"],
            rdate=["also-bad"],
        )
        assert isinstance(_event_is_past(ev), bool)
        assert _event_is_past(ev) is False  # future anchor, degraded one-off
        assert _format_event_datetime(ev) == "Tuesday, December 1, 9:00 AM"


def test_malformed_rrule_with_valid_rdate_uses_rdate():
    # A broken rrule must not discard a valid future RDATE.
    with patch("app.main.now_lake_havasu", return_value=REF):
        ev = _ev(
            date=date(2024, 1, 1),
            start_time=time(9, 0),
            rrule="not an rrule at all",
            is_recurring=True,
            rdate=["2026-07-04"],
        )
        assert _event_is_past(ev) is False
        assert "July 4" in _format_event_datetime(ev)


def test_is_past_uses_end_date_when_event_spans_into_future():
    with patch("app.main.now_lake_havasu", return_value=REF):
        ev = _ev(date=date(2026, 6, 3), end_date=date(2026, 6, 6))
        assert _event_is_past(ev) is False


# --- Event-link rendering: friendly label + source attribution byline --------


def test_link_domain_strips_www():
    assert _link_domain("https://www.riverscenemagazine.com/events/x") == "riverscenemagazine.com"
    assert _link_domain("https://allevents.in/lake-havasu/y") == "allevents.in"
    assert _link_domain("") == ""
    assert _link_domain(None) == ""


def test_link_label_falls_back_when_no_domain():
    assert _link_label("https://foundryhavasu.com/e") == "foundryhavasu.com"
    assert _link_label(None) == "Visit event page"


def test_event_link_html_shows_domain_not_raw_url():
    out = _event_link_html("https://www.riverscenemagazine.com/events/movies", None)
    assert "Event Link:" in out
    assert ">riverscenemagazine.com</a>" in out
    # the raw URL path is not used as the visible link text
    assert ">https://www.riverscenemagazine.com/events/movies</a>" not in out


def test_event_link_html_renders_source_byline_when_distinct():
    out = _event_link_html(
        "https://starcinemashavasu.com/", "https://www.riverscenemagazine.com/events/x"
    )
    assert 'class="ev-source"' in out
    assert "Source:" in out
    assert ">riverscenemagazine.com</a>" in out


def test_event_link_html_no_byline_when_source_same_site():
    out = _event_link_html("https://foundryhavasu.com/e", "https://foundryhavasu.com/other")
    assert "ev-source" not in out


def test_event_link_html_source_only_links_to_source():
    # No event_url: source becomes the primary link, and there's no redundant byline.
    out = _event_link_html(None, "https://havasis.org/")
    assert ">havasis.org</a>" in out
    assert "ev-source" not in out


def test_event_link_html_empty_when_no_urls():
    assert _event_link_html(None, None) == ""
    assert _event_link_html("", "") == ""


def test_venue_profile_url_links_event_to_provider_profile() -> None:
    """§1: an event whose venue has a live directory page resolves to that
    /provider/<slug> link; an event with no published venue profile resolves
    to None (plain text)."""
    import uuid

    from app.db.database import SessionLocal
    from app.db.models import Entity, Event, Provider

    src = f"test-venue-link-{uuid.uuid4().hex[:8]}"
    slug = f"test-lanes-{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        ent = Entity(
            entity_type="commercial", slug=f"ent-{uuid.uuid4().hex[:8]}",
            name="Test Lanes", source=src,
        )
        db.add(ent)
        db.flush()
        db.add(
            Provider(
                provider_name="Test Lanes", category="Bowling", slug=slug,
                is_active=True, draft=False, source=src, entity_id=ent.id,
            )
        )
        linked = Event(
            title="Night", normalized_title="night", date=date(2026, 6, 18),
            start_time=time(19, 0), end_time=None, location_name="Test Lanes",
            location_normalized="test lanes", description="d", event_url="",
            tags=[], status="live", source=src, created_by="seed", entity_id=ent.id,
        )
        db.add(linked)
        # A second entity with NO provider -> event resolves to no link.
        bare = Entity(
            entity_type="commercial", slug=f"bare-{uuid.uuid4().hex[:8]}",
            name="Nowhere", source=src,
        )
        db.add(bare)
        db.flush()
        unlinked = Event(
            title="Pop-up", normalized_title="pop-up", date=date(2026, 6, 18),
            start_time=time(19, 0), end_time=None, location_name="Nowhere",
            location_normalized="nowhere", description="d", event_url="",
            tags=[], status="live", source=src, created_by="seed", entity_id=bare.id,
        )
        db.add(unlinked)
        db.commit()
        assert _venue_profile_url(db, linked) == f"/provider/{slug}"
        assert _venue_profile_url(db, unlinked) is None
