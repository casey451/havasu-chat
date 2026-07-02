"""Phase-7 events + sitemap hygiene (master site audit §5 + §6.5).

* CVB site-footer boilerplate is stripped from event descriptions (ingest via
  clean_event_description; the backfill script repairs existing rows);
* event dates render the YEAR when not in the current calendar year;
* sitemap-events excludes past one-offs (recurring series stay — their anchor
  date being past is normal) using the Lake Havasu LOCAL date;
* sitemap-pages lists the editorial guide pages; /kids 301s to /family.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Event
from app.events.description_clean import clean_event_description, strip_cvb_boilerplate
from app.main import app

_FOOTER = (
    "Stay Connected Go Lake Havasu Visitor Center 422 English Village | Lake "
    "Havasu City, AZ 86403 (800) 242-8278 314 London Bridge Road | Lake Havasu "
    "City, AZ 86403 Who We Are"
)


# --- CVB footer strip ----------------------------------------------------------


def test_strip_cvb_boilerplate_truncates_footer():
    body = "Buses by the Bridge is a huge VW gathering on the island every January."
    assert strip_cvb_boilerplate(f"{body} {_FOOTER}") == body
    # Variant without the "Stay Connected" lead-in.
    assert strip_cvb_boilerplate(
        f"{body} Go Lake Havasu Visitor Center 422 English Village, Lake Havasu City"
    ) == body


def test_strip_cvb_boilerplate_passthrough_and_idempotent():
    body = "A concert with real prose. Stay Connected is not cut mid-sentence here."
    # "Stay Connected" NOT followed by the visitor-center block is left alone
    # (only the trailing form is chrome).
    assert strip_cvb_boilerplate(body) == body
    cleaned = strip_cvb_boilerplate(f"Real prose here for everyone. {_FOOTER}")
    assert strip_cvb_boilerplate(cleaned) == cleaned
    assert strip_cvb_boilerplate(None) == ""


def test_clean_event_description_applies_footer_strip():
    body = "The Liberty Quartet performs gospel favorites at the community center."
    out = clean_event_description(f"{body} {_FOOTER}")
    assert "Visitor Center" not in out
    assert "Stay Connected" not in out
    assert body in out


# --- year rendering ------------------------------------------------------------


def _ev(d: date) -> SimpleNamespace:
    return SimpleNamespace(
        date=d, start_time=None, end_time=None,
        rrule=None, rdate=None, is_recurring=False,
    )


def test_event_datetime_shows_year_when_not_current():
    from app.main import _format_event_datetime

    now_year = now_lake_havasu().year
    next_jan = date(now_year + 1, 1, 14)
    label = _format_event_datetime(_ev(next_jan))
    assert str(now_year + 1) in label, label

    this_year_day = now_lake_havasu().date() + timedelta(days=7)
    if this_year_day.year == now_year:  # skip the year-boundary week
        label2 = _format_event_datetime(_ev(this_year_day))
        assert str(now_year) not in label2, label2


# --- sitemap-events past filter --------------------------------------------------


def test_sitemap_events_excludes_past_oneoffs():
    from app.main import _build_sitemap_events_xml

    today = now_lake_havasu().date()
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        past = Event(title=f"Past Oneoff {suf}", normalized_title=f"past oneoff {suf}",
                     date=today - timedelta(days=30), start_time=time(0, 0),
                     location_name="Test Venue", location_normalized="test venue", description="x",
                     status="live", source="test")
        future = Event(title=f"Future Oneoff {suf}", normalized_title=f"future oneoff {suf}",
                       date=today + timedelta(days=30), start_time=time(0, 0),
                       location_name="Test Venue", location_normalized="test venue", description="x",
                       status="live", source="test")
        recurring = Event(title=f"Weekly Series {suf}", normalized_title=f"weekly series {suf}",
                          date=today - timedelta(days=400), start_time=time(0, 0),
                          location_name="Test Venue", location_normalized="test venue", description="x",
                          status="live", source="test", is_recurring=True,
                          rrule="FREQ=WEEKLY;BYDAY=SA")
        for ev in (past, future, recurring):
            db.add(ev)
        db.commit()
        ids = {"past": past.id, "future": future.id, "recurring": recurring.id}
    try:
        xml = _build_sitemap_events_xml()
        assert f"/events/{ids['future']}" in xml
        assert f"/events/{ids['recurring']}" in xml
        assert f"/events/{ids['past']}" not in xml
    finally:
        with SessionLocal() as db:
            db.query(Event).filter(Event.id.in_(list(ids.values()))).delete(
                synchronize_session=False)
            db.commit()


# --- sitemap-pages guide pages + /kids redirect ----------------------------------


def test_sitemap_pages_lists_guide_pages():
    from app.main import _build_sitemap_pages_xml

    xml = _build_sitemap_pages_xml()
    for path in ("/lake", "/night", "/family", "/seniors"):
        assert f"{path}</loc>" in xml, path


def test_kids_redirects_to_family():
    r = TestClient(app).get("/kids", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/family"
