"""WP-4: venue shape validation + go_lake_havasu structured-location parsing.

Covers the two audit cases (Farmers-Market / Visitor-Center and Buoy / organizer-
suite) where the venue must come out clean -- never the organizer block or page
footer -- plus the shape-validation rejections (multi-paragraph venue rejected,
dict leak rejected, description-prefix rejected) and the fbclid/UTM strip.
"""

from __future__ import annotations

from app.events.scrapers.base import (
    VENUE_NAME_MAX_LEN,
    clean_venue_shape,
    is_valid_venue_shape,
)
from app.events.scrapers.go_lake_havasu import (
    GoLakeHavasuClient,
    strip_tracking_params,
)


# --------------------------------------------------------------------------- #
# Shape validation.
# --------------------------------------------------------------------------- #
def test_short_venue_name_is_valid() -> None:
    assert is_valid_venue_shape("Lake Havasu Visitor Center")
    assert is_valid_venue_shape("Buoy 5")


def test_empty_venue_is_invalid() -> None:
    assert not is_valid_venue_shape("")
    assert not is_valid_venue_shape("   ")
    assert not is_valid_venue_shape(None)


def test_multi_paragraph_venue_rejected() -> None:
    blob = "Come join us downtown!\n\nThis weekend only, vendors from across AZ."
    assert not is_valid_venue_shape(blob)


def test_overlong_venue_rejected() -> None:
    long_prose = "x" * (VENUE_NAME_MAX_LEN + 1)
    assert not is_valid_venue_shape(long_prose)


def test_postaladdress_dict_leak_rejected() -> None:
    leak = "{'@type': 'PostalAddress', 'streetAddress': '314 London Bridge Rd'}"
    assert not is_valid_venue_shape(leak)


def test_description_prefix_rejected() -> None:
    desc = (
        "Do you have a moonshot business idea or an existing business you'd "
        "like to expand? Tell us more about it!"
    )
    # The venue field echoing the opening of the description body is corruption.
    assert not is_valid_venue_shape(desc[:90], description=desc)


def test_clean_venue_shape_keeps_good_drops_bad() -> None:
    assert clean_venue_shape("English Village") == "English Village"
    assert clean_venue_shape("a\n\nb") is None
    assert clean_venue_shape("   ") is None


# --------------------------------------------------------------------------- #
# go_lake_havasu structured-location parsing (audit cases).
# --------------------------------------------------------------------------- #
def _run_single(client: GoLakeHavasuClient, list_html: str, detail_html: str):
    def fake_fetch(url, **kwargs):
        return list_html if url.endswith("/events/") else detail_html

    import pytest

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(client, "fetch_text", fake_fetch)
    try:
        return client.run({})
    finally:
        monkeypatch.undo()


# Audit case 1: Farmers Market -- the real venue is the Visitor Center, parsed
# from the JSON-LD location.name; the organizer block / footer must NOT leak in.
FARMERS_LIST = '<a href="/events/lake-havasu-farmers-market/">Farmers Market</a>'
FARMERS_DETAIL = """
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Event","name":"Lake Havasu Farmers Market",
 "startDate":"2026-06-06T08:00:00-07:00","endDate":"2026-06-06T12:00:00-07:00",
 "location":{"@type":"Place","name":"Lake Havasu Visitor Center",
   "address":{"@type":"PostalAddress","streetAddress":"314 London Bridge Rd",
     "addressLocality":"Lake Havasu City","addressRegion":"AZ","postalCode":"86403"}},
 "organizer":{"@type":"Organization","name":"Go Lake Havasu, Suite 100, 314 London Bridge Rd"},
 "description":"Fresh local produce and crafts every Saturday morning.",
 "url":"https://www.golakehavasu.com/events/lake-havasu-farmers-market/"}
</script>
"""


def test_farmers_market_venue_is_visitor_center_not_organizer() -> None:
    payloads = _run_single(GoLakeHavasuClient(), FARMERS_LIST, FARMERS_DETAIL)
    assert payloads
    p = payloads[0]
    assert p.venue_name == "Lake Havasu Visitor Center"
    assert "Suite 100" not in (p.venue_name or "")  # organizer block did not leak
    assert "Go Lake Havasu" not in (p.venue_name or "")
    assert p.address == "314 London Bridge Rd, Lake Havasu City, AZ, 86403"


# Audit case 2: Buoy event -- location.name is a description blob; there is no
# clean venue, so venue_name must come out NULL rather than the organizer suite
# address block or the prose.
BUOY_LIST = '<a href="/events/buoy-cleanup-day/">Buoy Cleanup</a>'
BUOY_DETAIL = """
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Event","name":"Buoy Cleanup Day",
 "startDate":"2026-06-10T09:00:00-07:00",
 "location":{"@type":"Place","name":"Join volunteers as we clean up the channel buoys! Bring gloves, water, and a hat. Meet at the launch ramp."},
 "organizer":{"@type":"Organization","name":"Channel Stewards, Organizer Suite 200, 100 Marina Blvd"},
 "description":"Help keep the channel clean. All ages welcome.",
 "url":"https://www.golakehavasu.com/events/buoy-cleanup-day/"}
</script>
"""


def test_buoy_event_venue_null_not_organizer_suite() -> None:
    payloads = _run_single(GoLakeHavasuClient(), BUOY_LIST, BUOY_DETAIL)
    assert payloads
    p = payloads[0]
    # The description-shaped location.name was rejected; no organizer fallback.
    assert p.venue_name is None
    assert p.venue_name is None or "Suite 200" not in p.venue_name


# --------------------------------------------------------------------------- #
# URL tracking-param strip (fbclid / UTM).
# --------------------------------------------------------------------------- #
def test_strip_fbclid_and_utm() -> None:
    url = "https://example.com/e/5?utm_source=fb&utm_medium=social&fbclid=ABC123&id=9"
    assert strip_tracking_params(url) == "https://example.com/e/5?id=9"


def test_strip_tracking_no_params_unchanged() -> None:
    assert strip_tracking_params("https://example.com/e/5") == "https://example.com/e/5"


def test_strip_tracking_none() -> None:
    assert strip_tracking_params(None) is None
    assert strip_tracking_params("") is None


FBCLID_LIST = '<a href="/events/fb-tracked/">FB Tracked</a>'
FBCLID_DETAIL = """
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Event","name":"FB Tracked Event",
 "startDate":"2026-06-12T18:00:00-07:00",
 "location":{"@type":"Place","name":"The Nautical"},
 "url":"https://www.golakehavasu.com/events/fb-tracked/?fbclid=XYZ&utm_campaign=june"}
</script>
"""


def test_ingest_strips_tracking_from_event_url() -> None:
    payloads = _run_single(GoLakeHavasuClient(), FBCLID_LIST, FBCLID_DETAIL)
    assert payloads
    assert "fbclid" not in payloads[0].event_url
    assert "utm_" not in payloads[0].event_url
