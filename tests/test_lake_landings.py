"""Phase 3c — Lake landings: collection, sponsor teaser, event permalink.

Sponsor is static (TestClient); collection + event permalink need seeded data,
so the templates are rendered directly with sample context. Event permalink
keeps the full Event JSON-LD the route pre-builds.
"""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.home.router import templates as _home_templates
from app.main import app
from app.main import templates as _main_templates


def _req(path: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def _ld(html: str) -> list[dict]:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


# ── sponsor teaser (static) ─────────────────────────────────────────────────

def test_lake_sponsor_teaser() -> None:
    b = TestClient(app).get("/sponsor?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_redesign.css" in b
    # v4.4 §7: /sponsor is a real advertiser landing — indexable now (noindex dropped).
    assert 'name="robots" content="noindex"' not in b
    assert "/portal/placements" in b
    assert b.count("<h1") == 1
    checker = _A11yChecker()
    checker.feed(b)
    assert not checker.finish()


# ── curated collection ──────────────────────────────────────────────────────

def test_lake_collection_renders_and_schema() -> None:
    collection = {
        "title": "Dog-friendly patios", "blurb": "Where your pup is as welcome as you.",
        "accent": "water",
        "places": [
            {"slug": "barley-bros", "image_url": "https://img.example/b.jpg", "name": "Barley Brothers", "where": "Bridgewater", "blurb": "Lake-view patio.", "meta_line": "★ 4.5 · Brewpub"},
            {"slug": None, "image_url": None, "name": "Riverside Lawn", "where": "Channel", "blurb": None, "meta_line": None},
        ],
    }
    html = _home_templates.env.get_template("collection_landing_lake.html").render(
        request=_req("/collection/dog-friendly-patios"), collection=collection,
        today_label="Thursday, June 18", active_tab="explore",
    )
    assert 'data-theme="lake"' in html
    assert "Dog-friendly patios" in html
    assert "/provider/barley-bros" in html  # provider-backed card links
    assert "Riverside Lawn" in html  # static card (no slug) still renders
    cp = next(b for b in _ld(html) if b.get("@type") == "CollectionPage")
    assert cp["mainEntity"]["itemListElement"][0]["name"] == "Barley Brothers"
    assert html.count("<h1") == 1
    checker = _A11yChecker()
    checker.feed(html)
    assert not checker.finish()


# ── event permalink (full Event JSON-LD) ────────────────────────────────────

def test_lake_event_permalink_renders_with_event_schema() -> None:
    event_jsonld = {
        "@context": "https://schema.org", "@type": "Event", "name": "Sunset Paddle",
        "startDate": "2026-06-20T18:00:00",
        "location": {"@type": "Place", "name": "Site Six"},
    }
    html = _main_templates.env.get_template("event_permalink_lake.html").render(
        request=_req("/events/42"), event_title="Sunset Paddle",
        og_description="A guided sunset kayak up the channel.", og_url="https://askhava.com/events/42",
        image_url=None, event_jsonld=event_jsonld, is_past=False,
        formatted_datetime="Saturday, June 20 · 6:00 PM", location_name="Site Six",
        cost="$25", cost_description="boards provided", host="Lake Co.", ics_url="/events/42.ics",
        description="Paddle up the channel as the sun drops.", contact_html="", event_link_html="",
        tags_html="", active_tab="events",
    )
    assert 'data-theme="lake"' in html
    assert "Sunset Paddle" in html
    assert "Saturday, June 20 · 6:00 PM" in html
    assert 'id="ev-share"' in html  # share button
    ev = next(b for b in _ld(html) if b.get("@type") == "Event")
    assert ev["name"] == "Sunset Paddle" and ev["startDate"] == "2026-06-20T18:00:00"
    assert html.count("<h1") == 1
    checker = _A11yChecker()
    checker.feed(html)
    assert not checker.finish()
