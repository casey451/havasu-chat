"""Guardrails: description cleaning, URL validation, location normalization,
and detail-page description enrichment (the bogus-listing fix)."""

from __future__ import annotations

from datetime import date

import pytest

from app.contrib.event_enrich import (
    description_from_detail_html,
    enrich_event_descriptions,
)
from app.contrib.event_record import EventRecord
from app.events.description_clean import (
    clean_event_description,
    is_synthetic_placeholder,
    normalize_location_text,
    valid_event_url,
)

# ---- clean_event_description -------------------------------------------------

def test_metadata_only_body_is_dropped() -> None:
    assert clean_event_description("Venue: 2146 McCulloch Blvd\nCategories: theater") == ""


def test_full_metadata_block_with_date_heading_is_dropped() -> None:
    raw = (
        "Saturday, June 21\nTime: 08:00 - 12:00\n\n"
        "Venue: 2144 McCulloch Blvd N\nOrganizer: Havasu Together\nCategories: Farmer's Market"
    )
    assert clean_event_description(raw) == ""


def test_legacy_community_placeholder_is_dropped() -> None:
    raw = "A-Z - community event in Lake Havasu City. See source listing for details."
    assert clean_event_description(raw) == ""


def test_real_prose_is_preserved() -> None:
    prose = "Live jazz on the patio every Friday with local musicians and happy-hour specials."
    assert clean_event_description(prose) == prose


def test_real_prose_survives_with_metadata_appended() -> None:
    raw = (
        "Saturday, June 21\nTime: 18:00 - 21:00\n\n"
        "Now taking reservations for this painting class. $40 includes canvas, materials, and a cocktail.\n\n"
        "Venue: London Bridge Resort\nCoordinates: 34.4,-114.3\nImage: https://x/y.jpg"
    )
    out = clean_event_description(raw)
    assert "painting class" in out
    assert "Venue:" not in out and "Coordinates:" not in out and "Image:" not in out


def test_too_short_body_is_dropped() -> None:
    assert clean_event_description("Open mic.") == ""


def test_empty_and_none() -> None:
    assert clean_event_description("") == ""
    assert clean_event_description(None) == ""


# ---- is_synthetic_placeholder ------------------------------------------------

def test_synth_title_location_date_detected() -> None:
    assert is_synthetic_placeholder(
        "Roadwork at Lake Havasu City on Jun 06, 2026.",
        title="Roadwork",
        location_name="Lake Havasu City",
        start_date=date(2026, 6, 6),
    )


def test_real_sentence_not_flagged_as_synth() -> None:
    assert not is_synthetic_placeholder(
        "Join us at the marina on June 6, 2026 for fireworks and live music.",
        title="Fireworks",
        location_name="Marina",
        start_date=date(2026, 6, 6),
    )


# ---- valid_event_url ---------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "https://info@ijsba.com/",      # email used as URL (production bug)
    "http://havasuchat.com/events",  # dead pre-rename host
    "mailto:a@b.com",
    "ijsba.com",                     # no scheme
    "https://localhost/",            # no dot in host
    "",
    None,
])
def test_invalid_urls_rejected(bad) -> None:
    assert valid_event_url(bad) is None


@pytest.mark.parametrize("good", [
    "https://www.facebook.com/x",
    "https://golakehavasu.com/events/x",
    "http://example.org/path?a=1",
])
def test_valid_urls_pass(good) -> None:
    assert valid_event_url(good) == good


# ---- normalize_location_text -------------------------------------------------

def test_glued_city_gets_space() -> None:
    assert normalize_location_text("2144 McCulloch Blvd NLake Havasu City, AZ 86403") == \
        "2144 McCulloch Blvd N Lake Havasu City, AZ 86403"


def test_mccolloch_internal_caps_untouched() -> None:
    assert normalize_location_text("2146 McCulloch Blvd") == "2146 McCulloch Blvd"


def test_no_address_tail_removed() -> None:
    assert normalize_location_text("McCulloch Plaza No Address Available") == "McCulloch Plaza"


# ---- description_from_detail_html -------------------------------------------

def test_description_from_jsonld() -> None:
    html = """<html><head>
      <script type="application/ld+json">
      {"@type":"Event","name":"A-Z","description":"A-Z is a high-energy local cover band playing rock and country favorites all night."}
      </script></head><body></body></html>"""
    out = description_from_detail_html(html)
    assert "cover band" in out


def test_description_from_og_when_no_jsonld() -> None:
    html = ('<html><head><meta property="og:description" '
            'content="Cruise-in car show with classic hot rods, food trucks, and live music downtown.">'
            "</head><body></body></html>")
    out = description_from_detail_html(html)
    assert "hot rods" in out


def test_description_from_html_ignores_placeholder_meta() -> None:
    html = ('<html><head><meta name="description" '
            'content="community event in Lake Havasu City. See source listing for details.">'
            "</head><body></body></html>")
    assert description_from_detail_html(html) == ""


# ---- enrich_event_descriptions ----------------------------------------------

def _rec(title, desc, url):
    return EventRecord(source="allevents", title=title, start_date=date(2026, 6, 6),
                       description=desc, url=url)


def test_enrich_fills_only_empty_descriptions() -> None:
    recs = [
        _rec("A-Z", "", "https://allevents.in/x/a-z"),
        _rec("Has Body", "This event has a perfectly good real description already, thanks.",
             "https://allevents.in/x/has-body"),
    ]
    pages = {
        "https://allevents.in/x/a-z":
            '<meta property="og:description" content="A-Z plays rock and country covers all night long downtown.">',
    }
    calls: list[str] = []

    def fetch_text(u: str):
        calls.append(u)
        return pages.get(u, "")

    n = enrich_event_descriptions(recs, fetch_text=fetch_text)
    assert n == 1
    assert "rock and country" in (recs[0].description or "")
    # The record that already had a body was never fetched.
    assert calls == ["https://allevents.in/x/a-z"]


def test_enrich_skips_invalid_url_and_swallows_errors() -> None:
    recs = [
        _rec("No URL", "", None),
        _rec("Email URL", "", "https://info@ijsba.com/"),
        _rec("Boom", "", "https://allevents.in/x/boom"),
    ]

    def fetch_text(u: str):
        raise RuntimeError("network down")

    n = enrich_event_descriptions(recs, fetch_text=fetch_text)
    assert n == 0  # nothing enriched, no exception raised


def test_enrich_respects_max_fetch() -> None:
    recs = [_rec(f"E{i}", "", f"https://allevents.in/x/{i}") for i in range(5)]
    calls: list[str] = []

    def fetch_text(u: str):
        calls.append(u)
        return '<meta property="og:description" content="A real description that is plenty long to keep.">'

    enrich_event_descriptions(recs, fetch_text=fetch_text, max_fetch=2)
    assert len(calls) == 2
