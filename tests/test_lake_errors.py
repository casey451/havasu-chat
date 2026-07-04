"""Phase 5b — Lake Ink & Brass error pages (404 + 410).

The generic 404 goes through the StarletteHTTPException handler; the event error
goes through event_permalink. A removed event (status "deleted") now returns 410
Gone instead of the old soft-404 (it used to render full detail). Asserts the
flag-swap, desert default, the status codes, noindex, single-h1, and a11y.
"""

from __future__ import annotations

from datetime import date, time
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.main import app
from app.main import templates as _main_templates


def _req(path: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


def _seed_event(status: str) -> str:
    from app.db.database import SessionLocal
    from app.db.models import Event

    eid = f"evt-lake-err-{uuid4().hex[:10]}"
    with SessionLocal() as db:
        db.add(Event(
            id=eid, title="Removed Test Event", normalized_title="removed test event",
            date=date(2026, 7, 4), start_time=time(10, 0), status=status,
            location_name="Lake Havasu City", location_normalized="lake havasu city",
            description="A removed test event.", source="test-lake-errors",
        ))
        db.commit()
    return eid


# ── generic 404 (exception handler) ─────────────────────────────────────────

def test_lake_404_page() -> None:
    r = TestClient(app).get("/nonexistent-page-xyz?theme=lake")
    assert r.status_code == 404
    assert 'data-theme="lake"' in r.text
    assert "/static/styles/lake_redesign.css" in r.text  # v4.6 PR-1: base_plain v4 shell
    assert 'name="robots" content="noindex"' in r.text
    assert 'action="/categories"' in r.text  # search box → the directory
    assert 'href="/today"' in r.text  # Today link (Pre-answered 2)
    assert r.text.count("<h1") == 1
    assert not _a11y(r.text)


# ── event error: 404 (missing) + 410 (deleted) ──────────────────────────────

def test_event_missing_returns_404() -> None:
    r = TestClient(app).get(f"/events/{uuid4().hex}?theme=lake")
    assert r.status_code == 404
    assert 'data-theme="lake"' in r.text
    assert "Event not found." in r.text
    assert r.text.count("<h1") == 1
    assert not _a11y(r.text)


def test_event_deleted_returns_410_gone() -> None:
    client = TestClient(app)
    # lake variant
    eid = _seed_event("deleted")
    r = client.get(f"/events/{eid}?theme=lake")
    assert r.status_code == 410  # SEO: removed event is permanently Gone
    assert 'data-theme="lake"' in r.text
    assert "This event is gone." in r.text
    assert 'name="robots" content="noindex"' in r.text
    assert not _a11y(r.text)
    # Default (no theme param) still returns 410 (status code is theme-agnostic),
    # now rendered in lake. Fresh client so cookies don't carry over.
    eid2 = _seed_event("deleted")
    r2 = TestClient(app).get(f"/events/{eid2}")
    assert r2.status_code == 410
    assert 'data-theme="lake"' in r2.text


# ── direct template render (both branches) ──────────────────────────────────

def test_event_error_templates_render() -> None:
    for gone, code, phrase in ((False, "404", "Event not found."),
                               (True, "410", "This event is gone.")):
        html = _main_templates.env.get_template("event_not_found_lake.html").render(
            request=_req("/events/x"), gone=gone)
        assert 'data-theme="lake"' in html
        assert code in html
        assert phrase in html
        assert html.count("<h1") == 1
        assert not _a11y(html)
