from __future__ import annotations

from datetime import date, time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

import app.contrib.river_scene as river_scene
from app.contrib.river_scene import (
    EVENT_PAGE_HTTP_TIMEOUT,
    SITEMAP_HTTP_TIMEOUT,
    RiverSceneEvent,
    _http_get_text,
    fetch_and_parse_event,
    fetch_sitemap_urls,
    normalize_to_contribution,
)
from app.contrib.river_scene_pull import run_pull
from app.db.contribution_store import create_contribution
from app.db.database import SessionLocal
from app.db.models import Contribution, Event
from app.schemas.contribution import ContributionCreate
from app.schemas.event import EventCreate

FIXTURES = Path(__file__).resolve().parent.parent / "scripts" / "fixtures"


@pytest.fixture(autouse=True)
def _wipe_river_scene_tables() -> None:
    with SessionLocal() as db:
        db.query(Contribution).delete()
        db.query(Event).delete()
        db.commit()


@pytest.fixture(autouse=True)
def _no_polite_sleep() -> None:
    with patch("app.contrib.river_scene._sleep_polite"):
        yield


class TestRiverSceneHttpGetTextRetriesAndTimeouts:
    """Phase 8.10.1 — ``_http_get_text`` retry/timeout behavior (commit ``3972eec``)."""

    @pytest.fixture(autouse=True)
    def _no_backoff_sleep(self) -> None:
        # Retry loop uses ``time.sleep``; keep tests fast (polite sleep still mocked globally).
        with patch("app.contrib.river_scene.time.sleep"):
            yield

    def test_http_get_text_retries_on_timeout_then_succeeds(self) -> None:
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            if state["n"] == 1:
                raise httpx.ReadTimeout("test timeout", request=request)
            return httpx.Response(200, text="ok")

        url = "https://riverscenemagazine.com/events/retry-once/"
        to = httpx.Timeout(1.0)
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            out = _http_get_text(url, client, timeout=to)
        assert out == "ok"
        assert state["n"] == 2

    def test_http_get_text_retries_three_times_then_raises(self) -> None:
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            raise httpx.ReadTimeout("always", request=request)

        url = "https://riverscenemagazine.com/events/timeout-thrice/"
        to = httpx.Timeout(1.0)
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            with pytest.raises(httpx.ReadTimeout):
                _http_get_text(url, client, timeout=to)
        assert state["n"] == 3

    def test_http_get_text_retries_on_5xx_then_succeeds(self) -> None:
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            if state["n"] == 1:
                return httpx.Response(503, text="busy")
            return httpx.Response(200, text="recovered")

        url = "https://riverscenemagazine.com/events/five-oh-three/"
        to = httpx.Timeout(1.0)
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            out = _http_get_text(url, client, timeout=to)
        assert out == "recovered"
        assert state["n"] == 2

    def test_http_get_text_does_not_retry_on_4xx(self) -> None:
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            return httpx.Response(404, text="missing")

        url = "https://riverscenemagazine.com/events/not-found/"
        to = httpx.Timeout(1.0)
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            with pytest.raises(httpx.HTTPStatusError) as ei:
                _http_get_text(url, client, timeout=to)
        assert ei.value.response.status_code == 404
        assert state["n"] == 1

    def test_http_get_text_mixed_5xx_and_timeout(self) -> None:
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            if state["n"] == 1:
                return httpx.Response(500, text="err")
            if state["n"] == 2:
                raise httpx.ReadTimeout("after 500", request=request)
            return httpx.Response(200, text="ok")

        url = "https://riverscenemagazine.com/events/mixed/"
        to = httpx.Timeout(1.0)
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            out = _http_get_text(url, client, timeout=to)
        assert out == "ok"
        assert state["n"] == 3

    def test_fetch_sitemap_urls_uses_sitemap_timeout(self) -> None:
        with patch.object(river_scene, "_http_get_text", wraps=river_scene._http_get_text) as spy:
            with _client_for_sitemap_test() as client:
                fetch_sitemap_urls(client=client)
        assert spy.call_count >= 1
        for call in spy.call_args_list:
            assert call.kwargs.get("timeout") == SITEMAP_HTTP_TIMEOUT

    def test_fetch_and_parse_event_uses_event_timeout(self) -> None:
        html = """<!DOCTYPE html><html><head><title>RiverScene Magazine | Timeout Probe</title></head>
<body><div class="entry-content"><p>Body.</p>
<table><tr><td>Start Date</td><td>June 15, 2026</td></tr></table></div></body></html>"""
        u = "https://riverscenemagazine.com/events/timeout-probe/"
        with patch.object(river_scene, "_http_get_text", wraps=river_scene._http_get_text) as spy:
            with _html_client(html, u) as client:
                rse = fetch_and_parse_event(u, client=client, today=date(2026, 6, 1))
        assert rse is not None
        assert spy.call_count == 1
        assert spy.call_args.kwargs.get("timeout") == EVENT_PAGE_HTTP_TIMEOUT


def _client_for_sitemap_test() -> httpx.Client:
    index = (FIXTURES / "river_scene_sitemap_index.xml").read_text(encoding="utf-8")
    sub = (FIXTURES / "river_scene_events_sitemap.xml").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("/wp-sitemap.xml"):
            return httpx.Response(200, text=index)
        if "wp-sitemap-posts-events" in u:
            return httpx.Response(200, text=sub)
        return httpx.Response(404, text="not found")

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        timeout=5.0,
        follow_redirects=True,
    )


def test_fetch_sitemap_urls_parses_index_and_sub() -> None:
    with _client_for_sitemap_test() as client:
        urls = fetch_sitemap_urls(client=client)
    assert len(urls) == 3
    assert "https://riverscenemagazine.com/events/single-day/" in urls
    assert "https://riverscenemagazine.com/events/multi-day/" in urls
    assert "https://riverscenemagazine.com/events/third/" in urls


def _html_client(html: str, page_url: str = "https://riverscenemagazine.com/events/x/") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).rstrip("/") == page_url.rstrip("/"):
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0, follow_redirects=True)


def test_fetch_and_parse_single_day_event() -> None:
    html = """<!DOCTYPE html><html><head><title>RiverScene Magazine | One Day Fest</title></head>
<body><div class="entry-content"><p>Only one day of fun.</p>
<table><tr><td>Start Date</td><td>June 15, 2026</td></tr>
<tr><td>Time</td><td>9:00 am</td></tr></table></div></body></html>"""
    u = "https://riverscenemagazine.com/events/one-day/"
    with _html_client(html, u) as client:
        rse = fetch_and_parse_event(u, client=client, today=date(2026, 6, 1))
    assert rse is not None
    assert rse.title == "One Day Fest"
    assert rse.start_date == date(2026, 6, 15)
    assert rse.end_date == date(2026, 6, 15)
    assert "Only one day of fun" in rse.description_html


def test_fetch_and_parse_multi_day_event() -> None:
    html = (FIXTURES / "river_scene_event_detail.html").read_text(encoding="utf-8")
    u = "https://riverscenemagazine.com/events/desert-storm-racing/"
    with _html_client(html, u) as client:
        rse = fetch_and_parse_event(u, client=client, today=date(2026, 4, 1))
    assert rse is not None
    assert rse.title == "Desert Storm Racing"
    assert rse.start_date == date(2026, 4, 22)
    assert rse.end_date == date(2026, 4, 25)
    assert "Desert Storm" in rse.description_html


def test_fetch_and_parse_past_event_returns_none() -> None:
    html = (FIXTURES / "river_scene_event_past.html").read_text(encoding="utf-8")
    u = "https://riverscenemagazine.com/events/old/"
    with _html_client(html, u) as client:
        rse = fetch_and_parse_event(u, client=client, today=date(2026, 6, 1))
    assert rse is None


def test_fetch_and_parse_malformed_returns_none() -> None:
    html = "<html><body><p>No event table here.</p></body></html>"
    u = "https://riverscenemagazine.com/events/bad/"
    with _html_client(html, u) as client:
        rse = fetch_and_parse_event(u, client=client, today=date(2026, 1, 1))
    assert rse is None


def test_normalize_single_day() -> None:
    rse = RiverSceneEvent(
        title="T",
        url="https://riverscenemagazine.com/e/",
        start_date=date(2026, 6, 15),
        end_date=date(2026, 6, 15),
        start_time=time(9, 0),
        end_time=time(9, 0),
        description_html="<p>Hello</p>",
        venue_name=None,
        venue_address=None,
        organizer=None,
        category_slugs=[],
    )
    cc = normalize_to_contribution(rse)
    notes = cc.submission_notes or ""
    assert "Date: June 15, 2026" in notes
    first_date_line = [ln for ln in notes.splitlines() if ln.startswith("Date:")][0]
    assert "–" not in first_date_line


def test_normalize_multi_day() -> None:
    rse = RiverSceneEvent(
        title="T",
        url="https://riverscenemagazine.com/e/",
        start_date=date(2026, 6, 10),
        end_date=date(2026, 6, 12),
        start_time=time(8, 0),
        end_time=time(8, 0),
        description_html="x",
        venue_name=None,
        venue_address=None,
        organizer=None,
        category_slugs=[],
    )
    cc = normalize_to_contribution(rse)
    notes = cc.submission_notes or ""
    assert f"Date: June 10\u201312, 2026" in notes


def test_normalize_strips_html() -> None:
    rse = RiverSceneEvent(
        title="T",
        url="https://riverscenemagazine.com/e/",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        start_time=time(10, 0),
        end_time=time(10, 0),
        description_html="<p>Line <strong>one</strong>.</p>",
        venue_name=None,
        venue_address=None,
        organizer=None,
        category_slugs=[],
    )
    cc = normalize_to_contribution(rse)
    assert "<" not in (cc.submission_notes or "")
    assert "strong" not in (cc.submission_notes or "").lower()


def test_pull_skips_known_url_without_fetch(capsys: pytest.CaptureFixture[str]) -> None:
    url = "https://riverscenemagazine.com/events/dup-test/"
    with SessionLocal() as db:
        create_contribution(
            db,
            ContributionCreate(
                entity_type="event",
                submission_name="Already queued",
                submission_url=url,
                submission_notes="Z" * 22,
                source="river_scene_import",
            ),
        )

    index = (FIXTURES / "river_scene_sitemap_index.xml").read_text(encoding="utf-8")
    sub = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{url}</loc><lastmod>2026-04-20</lastmod></url>
</urlset>"""

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        requested.append(u)
        if u.endswith("/wp-sitemap.xml"):
            return httpx.Response(200, text=index)
        if "wp-sitemap-posts-events" in u:
            return httpx.Response(200, text=sub)
        if u.rstrip("/") == url.rstrip("/"):
            return httpx.Response(200, text="<html><body>should not fetch</body></html>")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0, follow_redirects=True)
    with client:
        rc = run_pull(date(2026, 6, 1), dry_run=False, http_client=client)
    assert rc == 0
    assert not any(u.rstrip("/") == url.rstrip("/") for u in requested)
    assert sum(1 for u in requested if "wp-sitemap" in u or "sitemap-posts-events" in u) == 2
    out = capsys.readouterr().out
    assert any(
        ln.strip().startswith("skipped_duplicate:") and ln.split()[-1] == "1" for ln in out.splitlines()
    )


def test_pull_seed_overlap_flag() -> None:
    d = date(2026, 7, 4)
    with SessionLocal() as db:
        db.add(
            Event.from_create(
                EventCreate(
                    title="Farmers Market Downtown",
                    date=d,
                    start_time="08:00:00",
                    end_time=None,
                    location_name="Downtown",
                    description="A weekly community farmers market in town.",
                    event_url="https://example.com/seed-fm",
                    contact_name=None,
                    contact_phone=None,
                    tags=["__seed__:lhc_001"],
                    is_recurring=True,
                    embedding=None,
                    status="live",
                    created_by="seed",
                )
            )
        )
        db.commit()

    html = f"""<!DOCTYPE html><html><head><title>RiverScene Magazine | Farmer's Market downtown</title></head>
<body><div class="entry-content"><p>Produce and more.</p>
<table><tr><td>Start Date</td><td>{d.strftime("%B %d, %Y")}</td></tr></table>
</div></body></html>"""
    ev_url = "https://riverscenemagazine.com/events/fm-test/"
    index = (FIXTURES / "river_scene_sitemap_index.xml").read_text(encoding="utf-8")
    sub = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{ev_url}</loc><lastmod>2026-04-20</lastmod></url>
</urlset>"""

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("/wp-sitemap.xml"):
            return httpx.Response(200, text=index)
        if "wp-sitemap-posts-events" in u:
            return httpx.Response(200, text=sub)
        if u.rstrip("/") == ev_url.rstrip("/"):
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0, follow_redirects=True)
    with client:
        run_pull(d, dry_run=False, http_client=client)

    with SessionLocal() as db:
        row = (
            db.query(Contribution)
            .filter(Contribution.source == "river_scene_import")
            .order_by(Contribution.id.desc())
            .first()
        )
    assert row is not None
    assert row.submission_notes is not None
    assert "[POSSIBLE DUPLICATE OF SEED EVENT:" in row.submission_notes
    assert "Farmers Market Downtown" in row.submission_notes


def test_pull_dry_run() -> None:
    html = """<!DOCTYPE html><html><head><title>RiverScene Magazine | Dry Run Ev</title></head>
<body><div class="entry-content"><p>Notes here long enough.</p>
<table><tr><td>Start Date</td><td>September 1, 2026</td></tr></table></div></body></html>"""
    ev_url = "https://riverscenemagazine.com/events/dr/"
    index = (FIXTURES / "river_scene_sitemap_index.xml").read_text(encoding="utf-8")
    sub = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{ev_url}</loc><lastmod>2026-04-20</lastmod></url>
</urlset>"""

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("/wp-sitemap.xml"):
            return httpx.Response(200, text=index)
        if "wp-sitemap-posts-events" in u:
            return httpx.Response(200, text=sub)
        if u.rstrip("/") == ev_url.rstrip("/"):
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0, follow_redirects=True)
    with SessionLocal() as db:
        before = db.query(Contribution).count()
    with client:
        run_pull(date(2026, 8, 1), dry_run=True, http_client=client)
    with SessionLocal() as db:
        after = db.query(Contribution).count()
    assert before == after


def test_pull_past_event_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    ev_url = "https://riverscenemagazine.com/events/past-only/"
    index = (FIXTURES / "river_scene_sitemap_index.xml").read_text(encoding="utf-8")
    sub = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{ev_url}</loc><lastmod>2020-01-01</lastmod></url>
</urlset>"""

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("/wp-sitemap.xml"):
            return httpx.Response(200, text=index)
        if "wp-sitemap-posts-events" in u:
            return httpx.Response(200, text=sub)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0, follow_redirects=True)
    with patch("app.contrib.river_scene_pull.fetch_and_parse_event", return_value=None):
        with client:
            rc = run_pull(date(2026, 8, 1), dry_run=False, http_client=client)
    assert rc == 0
    with SessionLocal() as db:
        n = db.query(Contribution).count()
    assert n == 0
    out = capsys.readouterr().out
    assert any(
        ln.strip().startswith("skipped_past_or_unparseable:") and ln.split()[-1] == "1"
        for ln in out.splitlines()
    )


def test_river_scene_pull_auto_approves_contribution() -> None:
    html = """<!DOCTYPE html><html><head><title>RiverScene Magazine | Auto Approve Ev</title></head>
<body><div class="entry-content"><p>This event has enough detail for approval payload.</p>
<table><tr><td>Start Date</td><td>September 2, 2026</td></tr>
<tr><td>Time</td><td>9:00 am</td></tr>
<tr><td>Venue</td><td>Rotary Park</td></tr></table></div></body></html>"""
    ev_url = "https://riverscenemagazine.com/events/auto-approve/"
    index = (FIXTURES / "river_scene_sitemap_index.xml").read_text(encoding="utf-8")
    sub = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{ev_url}</loc><lastmod>2026-04-20</lastmod></url>
</urlset>"""

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("/wp-sitemap.xml"):
            return httpx.Response(200, text=index)
        if "wp-sitemap-posts-events" in u:
            return httpx.Response(200, text=sub)
        if u.rstrip("/") == ev_url.rstrip("/"):
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0, follow_redirects=True)
    with client:
        rc = run_pull(date(2026, 8, 1), dry_run=False, http_client=client)
    assert rc == 0

    with SessionLocal() as db:
        row = db.query(Contribution).order_by(Contribution.id.desc()).first()
        assert row is not None
        assert row.source == "river_scene_import"
        assert row.status == "approved"
        assert row.created_event_id is not None
        ev = db.get(Event, row.created_event_id)
        assert ev is not None
        assert ev.source == "river_scene_import"


def test_river_scene_pull_does_not_auto_approve_user_submission() -> None:
    rse = RiverSceneEvent(
        title="User Source Should Stay Pending",
        url="https://riverscenemagazine.com/events/no-auto/",
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 10),
        start_time=time(9, 0),
        end_time=time(11, 0),
        description_html="<p>Sufficiently long description content for pending contribution path.</p>",
        venue_name="Community Center",
        venue_address=None,
        organizer=None,
        category_slugs=["community"],
    )
    payload = normalize_to_contribution(rse).model_copy(update={"source": "user_submission"})
    with patch("app.contrib.river_scene_pull.fetch_sitemap_urls", return_value=["https://riverscenemagazine.com/events/no-auto/"]):
        with patch("app.contrib.river_scene_pull.fetch_and_parse_event", return_value=rse):
            with patch("app.contrib.river_scene_pull.normalize_to_contribution", return_value=payload):
                with httpx.Client(
                    transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
                    timeout=5.0,
                    follow_redirects=True,
                ) as client:
                    rc = run_pull(date(2026, 8, 1), dry_run=False, http_client=client)
    assert rc == 0
    with SessionLocal() as db:
        row = db.query(Contribution).order_by(Contribution.id.desc()).first()
        assert row is not None
        assert row.source == "user_submission"
        assert row.status == "pending"
        assert row.created_event_id is None
        assert db.query(Event).count() == 0


def test_river_scene_pull_auto_approval_failure_leaves_contribution_pending(
    capsys: pytest.CaptureFixture[str],
) -> None:
    html = """<!DOCTYPE html><html><head><title>RiverScene Magazine | Auto Approve Fail</title></head>
<body><div class="entry-content"><p>This event will fail auto approval and stay pending.</p>
<table><tr><td>Start Date</td><td>October 1, 2026</td></tr>
<tr><td>Time</td><td>10:00 am</td></tr>
<tr><td>Venue</td><td>Nautical Beachfront</td></tr></table></div></body></html>"""
    ev_url = "https://riverscenemagazine.com/events/auto-approve-fail/"
    index = (FIXTURES / "river_scene_sitemap_index.xml").read_text(encoding="utf-8")
    sub = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{ev_url}</loc><lastmod>2026-04-20</lastmod></url>
</urlset>"""

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("/wp-sitemap.xml"):
            return httpx.Response(200, text=index)
        if "wp-sitemap-posts-events" in u:
            return httpx.Response(200, text=sub)
        if u.rstrip("/") == ev_url.rstrip("/"):
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0, follow_redirects=True)
    with patch("app.contrib.river_scene_pull.approve_contribution_as_event", side_effect=RuntimeError("boom")):
        with client:
            rc = run_pull(date(2026, 8, 1), dry_run=False, http_client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert any(ln.strip().startswith("auto_approval_failed:") and ln.split()[-1] == "1" for ln in out.splitlines())
    with SessionLocal() as db:
        row = db.query(Contribution).order_by(Contribution.id.desc()).first()
        assert row is not None
        assert row.status == "pending"
        assert row.created_event_id is None
        assert db.query(Event).count() == 0


def test_contribution_source_literal_accepts_river_scene_import() -> None:
    c = ContributionCreate(
        entity_type="event",
        submission_name="Test Event Name Here",
        submission_url="https://riverscenemagazine.com/event/x/",
        submission_notes="Y" * 22,
        source="river_scene_import",
    )
    assert c.source == "river_scene_import"


def test_approve_event_sets_is_recurring_heuristic() -> None:
    from app.contrib.approval_service import approve_contribution_as_event

    with SessionLocal() as db:
        c = create_contribution(
            db,
            ContributionCreate(
                entity_type="event",
                submission_name="Weekly market Saturday",
                submission_url="https://example.com/mkt-approve-test/",
                submission_notes="N" * 22,
                event_date=date(2026, 8, 10),
                event_time_start=time(9, 0),
                source="operator_backfill",
            ),
        )
        cid = c.id
    from app.schemas.contribution import EventApprovalFields

    evf = EventApprovalFields(
        title="Weekly market Saturday",
        description="Runs every Saturday morning in the park with vendors.",
        date=date(2026, 8, 10),
        start_time=time(9, 0),
        end_time=time(13, 0),
        location_name="City Park",
        event_url="https://example.com/mkt-approve-test/",
    )
    with SessionLocal() as db:
        ev = approve_contribution_as_event(db, cid, evf, ["outdoor"])
    assert ev.is_recurring is True
