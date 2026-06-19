"""Phase 9b — Star Cinemas (Veezi/Supabase ``sessions`` feed) scraper.

Fixtures mirror the live shape captured 2026-06-19 from the public Supabase
``sessions`` table joined to films/screens/sites.
"""

from __future__ import annotations

from datetime import date

from app.events.scrapers.star_cinemas import (
    StarCinemasClient,
    _parse_session_dt,
    _runtime_label,
)

# Two real-shaped sessions: a normal public showtime and a sold-out one whose
# status should still publish, plus one cancelled row that must be dropped.
SESSIONS_FIXTURE = [
    {
        "id": "55346",
        "session_datetime": "2026-06-19T11:35:00+00:00",
        "show_start": "2026-06-19T11:45:00+00:00",
        "status": "Open",
        "show_type": "Public",
        "seating_type": "Open",
        "is_sold_out": False,
        "web_session_url": "https://ticketing.uswest.veezi.com/purchase/55346?siteToken=abc",
        "film": {
            "id": "ST00001022",
            "title": "Toy Story 5",
            "rating": "PG",
            "genre": "Adventure",
            "runtime": 102,
            "director": "Andrew Stanton",
            "synopsis": "The toys are back.",
            "poster_url": "https://ticketing.uswest.veezi.com/Media/Poster?code=1&isHighRes=true",
            "release_date": "2026-06-19",
        },
        "screen": {"screen_name": "Theater 6"},
        "site": {
            "name": "Star Cinemas",
            "address": "5601 Hwy 95 Bldg I",
            "city": None,
            "state": None,
            "timezone": "US Mountain Standard Time",
        },
    },
    {
        "id": "55311",
        "session_datetime": "2026-06-19T19:45:00+00:00",
        "show_start": "2026-06-19T19:55:00+00:00",
        "status": "Open",
        "show_type": "Public",
        "seating_type": "Open",
        "is_sold_out": True,
        "web_session_url": "https://ticketing.uswest.veezi.com/purchase/55311?siteToken=abc",
        "film": {
            "id": "ST00000996",
            "title": "Obsession",
            "rating": "R",
            "genre": "Horror",
            "runtime": 108,
            "director": "Curry Barker",
            "synopsis": "",
            "poster_url": "",
            "release_date": "2026-06-12",
        },
        "screen": {"screen_name": "Theater 7"},
        "site": {"name": "Star Cinemas", "address": "5601 Hwy 95 Bldg I"},
    },
    {
        "id": "99999",
        "session_datetime": "2026-06-20T10:00:00+00:00",
        "status": "Cancelled",
        "show_type": "Public",
        "is_sold_out": False,
        "web_session_url": "https://ticketing.uswest.veezi.com/purchase/99999",
        "film": {"id": "ST0", "title": "Cancelled Film", "rating": "PG"},
        "screen": {"screen_name": "Theater 1"},
        "site": {"name": "Star Cinemas"},
    },
]


def test_parse_session_dt_treats_naive_local() -> None:
    # +00:00 suffix is a serialization artifact; wall-clock components are local.
    dt = _parse_session_dt("2026-06-19T11:35:00+00:00")
    assert dt.tzinfo is None
    assert dt.hour == 11 and dt.minute == 35
    assert dt.date() == date(2026, 6, 19)


def test_runtime_label() -> None:
    assert _runtime_label(102) == "1 hr 42 min"
    assert _runtime_label(45) == "45 min"
    assert _runtime_label(0) is None
    assert _runtime_label(None) is None


def test_discover_skips_cancelled_and_titleless(monkeypatch) -> None:
    client = StarCinemasClient()
    monkeypatch.setattr(client, "_fetch_json", lambda url, **kw: SESSIONS_FIXTURE)
    hits = client.discover({"today": date(2026, 6, 19)})
    assert len(hits) == 2  # cancelled row dropped
    assert {h.source_stable_id for h in hits} == {"55346", "55311"}


def test_to_event_payload_maps_fields(monkeypatch) -> None:
    client = StarCinemasClient()
    monkeypatch.setattr(client, "_fetch_json", lambda url, **kw: SESSIONS_FIXTURE)
    payloads = client.run({"today": date(2026, 6, 19)})
    by_name = {p.name: p for p in payloads}

    toy = by_name["Toy Story 5"]
    assert toy.start_date == date(2026, 6, 19)
    assert toy.start_time.hour == 11 and toy.start_time.minute == 35
    assert toy.venue_name == "Star Cinemas"
    assert toy.event_url.startswith("https://ticketing.uswest.veezi.com/purchase/55346")
    assert toy.image_url and "Poster" in toy.image_url
    assert toy.category_slug == "movies"
    assert "movie" in toy.tags and "showtime" in toy.tags and "star-cinemas" in toy.tags
    assert "PG" in toy.description and "Adventure" in toy.description

    obsession = by_name["Obsession"]
    assert "sold-out" in obsession.tags  # sold-out still published, flagged via tag


def test_dedupe_keys_unique(monkeypatch) -> None:
    client = StarCinemasClient()
    monkeypatch.setattr(client, "_fetch_json", lambda url, **kw: SESSIONS_FIXTURE)
    hits = client.discover({"today": date(2026, 6, 19)})
    keys = [client.dedupe_key(h) for h in hits]
    assert len(set(keys)) == len(keys)
