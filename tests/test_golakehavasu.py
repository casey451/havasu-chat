"""golakehavasu.com -- sitemap discovery + event HTML parsing + contribution map."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.contrib.golakehavasu import (
    SITEMAP_INDEX_URL,
    GoLakeHavasuEvent,
    fetch_and_parse_event,
    fetch_sitemap_urls,
    normalize_to_contribution,
)

FIXTURES = Path(__file__).resolve().parent.parent / "scripts" / "fixtures"

EVENTS_SITEMAP_URL = "https://www.golakehavasu.com/sitemaps-1-event-default-1-sitemap.xml"
SOIREE_URL = "https://www.golakehavasu.com/events/a-soiree-of-ballet/"
MARKET_URL = "https://www.golakehavasu.com/events/lake-havasu-farmers-market/"
PAST_URL = "https://www.golakehavasu.com/events/old-past-event/"

TODAY = date(2026, 1, 1)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_polite_sleep():
    with patch("app.contrib.golakehavasu._sleep_polite"):
        yield


def _mock_client() -> httpx.Client:
    routes = {
        SITEMAP_INDEX_URL: _fixture("golakehavasu_sitemap_index.xml"),
        EVENTS_SITEMAP_URL: _fixture("golakehavasu_events_sitemap.xml"),
        SOIREE_URL: _fixture("golakehavasu_event_detail.html"),
        MARKET_URL: _fixture("golakehavasu_event_recurring.html"),
        PAST_URL: _fixture("golakehavasu_event_past.html"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="not found")
        return httpx.Response(200, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_sitemap_urls_follows_event_default_child() -> None:
    with _mock_client() as client:
        urls = fetch_sitemap_urls(client=client)
    assert urls == [SOIREE_URL, MARKET_URL, PAST_URL]


def test_parse_single_day_event_full_fields() -> None:
    with _mock_client() as client:
        ev = fetch_and_parse_event(SOIREE_URL, client=client, today=TODAY)
    assert ev is not None
    assert ev.title == "A Soiree of Ballet"
    assert ev.start_date == date(2026, 5, 29)
    assert ev.end_date == date(2026, 5, 29)
    assert ev.start_time == time(17, 0)
    assert ev.end_time == time(20, 0)
    assert ev.venue_name == "London Bridge Resort"
    assert ev.venue_address == "1477 Queens Bay, Lake Havasu City, AZ 86403"
    assert ev.lat == pytest.approx(34.471156)
    assert ev.lng == pytest.approx(-114.3454307)
    assert ev.image_url and ev.image_url.endswith("soiree.png")
    assert ev.organizer_url == "https://33805.danceticketing.com/r/5744/56354/"
    assert len(ev.description) > 20


def test_recurring_event_prefers_dom_date_over_stale_jsonld() -> None:
    # JSON-LD startDate is 2025-08-02 (stale); the rendered header shows the
    # correct next occurrence 2026-05-30. The DOM must win.
    with _mock_client() as client:
        ev = fetch_and_parse_event(MARKET_URL, client=client, today=TODAY)
    assert ev is not None
    assert ev.start_date == date(2026, 5, 30)
    assert ev.start_time == time(8, 0)
    assert ev.venue_name == "The KAWS"
    # The trailing phone line must not be mistaken for the street.
    assert ev.venue_address == "2144 McCulloch Blvd N, Lake Havasu City, AZ 86403"


def test_past_event_returns_none() -> None:
    with _mock_client() as client:
        ev = fetch_and_parse_event(PAST_URL, client=client, today=TODAY)
    assert ev is None


def test_normalize_to_contribution_fields() -> None:
    with _mock_client() as client:
        ev = fetch_and_parse_event(SOIREE_URL, client=client, today=TODAY)
    assert ev is not None
    c = normalize_to_contribution(ev)
    assert c.entity_type == "event"
    assert c.source == "go_lake_havasu"
    assert c.submission_name == "A Soiree of Ballet"
    assert c.source_url == "https://www.golakehavasu.com/events/a-soiree-of-ballet"
    assert str(c.submission_url).startswith("https://33805.danceticketing.com/")
    assert c.event_date == date(2026, 5, 29)
    assert c.event_time_start == time(17, 0)
    assert c.event_time_end == time(20, 0)
    notes = c.submission_notes or ""
    assert "Venue: London Bridge Resort" in notes
    assert "1477 Queens Bay" in notes
    assert "Coordinates: 34.471156,-114.3454307" in notes


def test_event_end_date_omitted_for_single_day() -> None:
    ev = GoLakeHavasuEvent(
        title="One Day",
        url="https://www.golakehavasu.com/events/one-day/",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        description="A single-day event with a description long enough.",
        venue_name="Somewhere",
        venue_address="1 Main St, Lake Havasu City, AZ 86403",
        lat=34.5,
        lng=-114.3,
        image_url=None,
        organizer_url=None,
    )
    c = normalize_to_contribution(ev)
    assert c.event_end_date is None


def test_run_pull_tolerates_removed_event_pages() -> None:
    """A 404 on one event page (CVB removed it but left the sitemap entry) is a
    skip, not a run failure — one stale entry was failing the whole cron."""
    from app.contrib.golakehavasu_pull import run_pull

    routes = {
        SITEMAP_INDEX_URL: _fixture("golakehavasu_sitemap_index.xml"),
        EVENTS_SITEMAP_URL: _fixture("golakehavasu_events_sitemap.xml"),
        # SOIREE_URL intentionally missing -> 404 (removed upstream)
        MARKET_URL: _fixture("golakehavasu_event_recurring.html"),
        PAST_URL: _fixture("golakehavasu_event_past.html"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="not found")
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with client:
        rc = run_pull(date(2026, 6, 6), dry_run=True, http_client=client)
    assert rc == 0
