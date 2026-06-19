"""Star Cinemas sources must be registered for the contributions pipeline.

Regression guard for a bug that the dry-run path could not catch: the scraper
and kids-series loader use `source` values that must be in the
``ContributionSource`` allow-list, and in the auto-approve tier so showtimes go
live on /movies instead of landing in the pending queue. The dry-run returns
before building a ``ContributionCreate``, so only a real write exercised this.
"""

from __future__ import annotations

from datetime import date, time

from app.contrib.approval_service import (
    auto_approve_event_sources,
    should_auto_approve_event,
)
from app.db.models import Contribution
from app.events.scrapers.base import EventPayload, event_payload_to_contribution

MOVIE_SOURCES = ("star_cinemas", "star_cinemas_kids_series")


def test_movie_sources_build_valid_contributions():
    for src in MOVIE_SOURCES:
        payload = EventPayload(
            name="Toy Story 5",
            entity_type="event",
            source=src,
            start_date=date(2026, 6, 22),
            start_time=time(11, 0),
            venue_name="Star Cinemas",
            description="PG · Adventure",
            event_url="https://ticketing.uswest.veezi.com/purchase/1",
            source_stable_url="https://ticketing.uswest.veezi.com/purchase/1",
            category_slug="movies",
        )
        contribution = event_payload_to_contribution(payload, scrape_source=src)
        assert contribution.source == src


def test_movie_sources_auto_approve():
    approved = auto_approve_event_sources()
    for src in MOVIE_SOURCES:
        assert src in approved
        c = Contribution(
            entity_type="event",
            source=src,
            submission_name="Toy Story 5",
            event_date=date(2026, 6, 22),
            event_time_start=time(11, 0),
        )
        assert should_auto_approve_event(c) is True


def test_kids_series_showings_have_unique_urls():
    # The contributions pipeline dedups on submission_url; a shared link would
    # collapse the whole series into one row. Each showing must be unique.
    from scripts.load_star_cinemas_kids_series import _payloads

    payloads = _payloads()
    urls = [p.event_url for p in payloads]
    assert urls, "kids series SERIES is empty"
    assert len(set(urls)) == len(urls)


def test_kids_series_titles_meet_min_length():
    # EventApprovalFields.title requires >= 3 chars; a 2-char title (e.g. "IF")
    # crashes the auto-approve path on apply.
    from scripts.load_star_cinemas_kids_series import SERIES

    for row in SERIES:
        assert len(row["title"]) >= 3, row["title"]
