"""2026-06 event data-quality fixes: time/venue prose extraction, cost parsing,
automotive/boating tagging, venue normalization, weekday-contradiction flagging,
host extraction, persisted-row dedupe guard, and the new structured fields.

No DB, no HTTP except the dedupe-guard test which uses the real SessionLocal the
other ingest tests in this repo use.
"""

from __future__ import annotations

from datetime import date, time

from app.contrib.event_enrich import _recover_time_venue_from_prose, enrich_event_records
from app.contrib.event_ingest import (
    _cost_for_record,
    _host_from_title,
    _live_music_tags,
    _tags,
    weekday_contradiction,
)
from app.contrib.event_record import (
    EventRecord,
    canonicalize_venue,
    extract_cost_from_text,
    extract_time_from_text,
    extract_venue_from_text,
    parse_jsonld_events,
)


def _rec(title: str, *, description: str = "", venue: str | None = None,
         start_date: date | None = None, start_time: time | None = None,
         tags: list[str] | None = None) -> EventRecord:
    return EventRecord(
        source="allevents",
        title=title,
        start_date=start_date or date(2026, 7, 1),
        start_time=start_time,
        venue_name=venue,
        description=description,
        tags=tags or [],
    )


# --------------------------------------------------------------------------- #
# 2.1 — start time + venue from description prose (the four real samples)
# --------------------------------------------------------------------------- #
def test_time_extract_annual_meeting() -> None:
    body = (
        "Join the Chamber for the 2026 Annual Meeting and Celebration of Business "
        "at London Bridge Resort. Doors open at 5:00 PM MST for networking."
    )
    assert extract_time_from_text(body) == time(17, 0)
    assert extract_venue_from_text(body) == "London Bridge Resort"


def test_time_extract_the_ogs() -> None:
    body = "The OGs take the stage at 317 S Lake Havasu Ave, doors at 7:00 PM."
    assert extract_time_from_text(body) == time(19, 0)
    assert extract_venue_from_text(body) == "317 S Lake Havasu Ave"


def test_time_extract_emmanuel_hangar24() -> None:
    body = "EMMANUEL Live at Hangar 24 starting 5:30 pm. An unforgettable night."
    assert extract_time_from_text(body) == time(17, 30)
    assert extract_venue_from_text(body) == "Hangar 24"


def test_time_extract_laveycraft_meetup() -> None:
    body = "Laveycraft LCOE Annual Meetup 2026 kicks off at 10:00 AM with check-in."
    assert extract_time_from_text(body) == time(10, 0)


def test_time_extract_handles_bare_ampm_and_out_of_range() -> None:
    assert extract_time_from_text("show at 5pm") == time(17, 0)
    assert extract_time_from_text("at 12 am") == time(0, 0)
    assert extract_time_from_text("at 12 pm") == time(12, 0)
    assert extract_time_from_text("no time here") is None


def test_recover_time_venue_from_prose_fills_thin_record() -> None:
    rec = _rec(
        "EMMANUEL Live",
        description="EMMANUEL Live at Hangar 24 starting 5:30 pm.",
        venue="Lake Havasu City",
        start_time=time(0, 0),
    )
    assert _recover_time_venue_from_prose(rec) is True
    assert rec.start_time == time(17, 30)
    assert rec.venue_name == "Hangar 24"


def test_recover_does_not_overwrite_real_time_or_named_venue() -> None:
    rec = _rec(
        "EMMANUEL Live",
        description="EMMANUEL Live at Hangar 24 starting 5:30 pm.",
        venue="The Nautical",
        start_time=time(18, 0),
    )
    _recover_time_venue_from_prose(rec)
    assert rec.start_time == time(18, 0)       # preserved
    assert rec.venue_name == "The Nautical"    # preserved


def test_enrich_no_jsonld_recovers_time_venue_from_prose() -> None:
    # Detail page has no Event JSON-LD, only an og:description with the time/venue.
    html_page = (
        '<html><head>'
        '<meta property="og:description" content="EMMANUEL Live at Hangar 24 '
        'starting 5:30 pm. A great show.">'
        "</head><body></body></html>"
    )
    rec = _rec("EMMANUEL Live", venue="Lake Havasu City", start_time=time(0, 0))
    rec.url = "https://allevents.in/lake-havasu-city/emmanuel/1"
    n = enrich_event_records([rec], fetch_text=lambda u: html_page, source="allevents")
    assert n == 1
    assert rec.start_time == time(17, 30)
    assert rec.venue_name == "Hangar 24"


# --------------------------------------------------------------------------- #
# 2.2 — cost parsing
# --------------------------------------------------------------------------- #
def test_cost_single_range_and_free() -> None:
    assert extract_cost_from_text("Tickets are $20 at the door.") == "$20"
    assert extract_cost_from_text("Admission $10 - $25 depending on tier.") == "$10-$25"
    assert extract_cost_from_text("Free admission, all welcome!") == "Free"
    assert extract_cost_from_text("A lovely evening of music.") is None


def test_cost_for_record_prefers_structured_offer() -> None:
    rec = _rec("Show", description="cover is $5")
    rec.raw = {"offers_price": "$15"}
    assert _cost_for_record(rec) == "$15"
    free = _rec("Free Show", description="no price listed")
    free.raw = {"is_free": True}
    assert _cost_for_record(free) == "Free"


def test_cost_from_jsonld_offers() -> None:
    html_page = """
    <html><head><script type="application/ld+json">
    {"@type":"Event","name":"Paid Show","startDate":"2026-12-03T19:00:00",
     "offers":{"@type":"Offer","price":"20.00","priceCurrency":"USD"}}
    </script></head></html>"""
    recs = parse_jsonld_events(html_page, source="allevents")
    assert recs[0].raw.get("offers_price") == "$20"


def test_cost_from_jsonld_free_offer() -> None:
    html_page = """
    <html><head><script type="application/ld+json">
    {"@type":"Event","name":"Free Show","startDate":"2026-12-03T19:00:00",
     "offers":{"@type":"Offer","price":"0"}}
    </script></head></html>"""
    recs = parse_jsonld_events(html_page, source="allevents")
    rec = recs[0]
    assert rec.raw.get("is_free") is True
    assert _cost_for_record(rec) == "Free"


# --------------------------------------------------------------------------- #
# 2.5 — automotive / boating tags; Motor Madness must not be music
# --------------------------------------------------------------------------- #
def test_motor_madness_not_music_but_automotive() -> None:
    rec = _rec(
        "Motor Madness Car Show",
        description="Classic cars, a DJ spinning oldies, and a dance for the crowd.",
        venue="Main Street",
    )
    tags = _tags(rec)
    assert "music" not in tags
    assert "automotive" in tags
    assert _live_music_tags(rec) == []


def test_cruise_in_is_automotive() -> None:
    assert "automotive" in _tags(_rec("Saturday Cruise-In"))


def test_boating_event_tagged() -> None:
    assert "lake-boating" in _tags(_rec("Annual Boat Parade on the Channel"))


def test_real_concert_still_music_even_with_cars_mentioned() -> None:
    # A genuine live-band event that mentions classic cars keeps music (strong sig).
    rec = _rec(
        "The Rockabilly Reunion",
        description="A weekend of live bands, classic cars, and dancing.",
        venue="London Bridge",
    )
    assert "music" in _tags(rec)


def test_car_show_with_live_band_headliner_keeps_music() -> None:
    rec = _rec(
        "Car Show & Concert",
        description="Show n shine all day, then a live band concert at 7pm.",
    )
    # Strong music signal (live band / concert) overrides the automotive guard.
    assert "music" in _tags(rec)


def test_widened_keywords_reduce_community_reliance() -> None:
    assert "festival" in _tags(_rec("Spring Festival & Parade"))
    assert "food-drink" in _tags(_rec("Downtown Wine Tasting"))
    assert "sports" in _tags(_rec("Havasu 5k Fun Run"))


# --------------------------------------------------------------------------- #
# 2.7 — venue normalization + weekday contradiction flag
# --------------------------------------------------------------------------- #
def test_canonicalize_collapses_doubled_city() -> None:
    assert (
        canonicalize_venue("Lake Havasu City, Lake Havasu City, AZ")
        == "Lake Havasu City, AZ"
    )
    assert canonicalize_venue("Rotary Park, Rotary Park") == "Rotary Park"
    assert canonicalize_venue("London Bridge Resort, AZ") == "London Bridge Resort, AZ"
    assert canonicalize_venue("") is None


def test_weekday_contradiction_flags_mismatch() -> None:
    # BMX Clinic listed on a Friday (2026-07-03 is a Friday) but body says Tue/Thu.
    rec = _rec(
        "BMX Clinic",
        description="Weekly skills clinic held Tue/Thu evenings at the track.",
        start_date=date(2026, 7, 3),
    )
    assert rec.start_date.weekday() == 4  # Friday
    assert weekday_contradiction(rec) is True


def test_weekday_no_contradiction_when_consistent_or_silent() -> None:
    # Body weekday matches the listed date (2026-07-02 is a Thursday).
    ok = _rec(
        "BMX Clinic",
        description="Skills clinic every Thursday.",
        start_date=date(2026, 7, 2),
    )
    assert weekday_contradiction(ok) is False
    # Body names no weekday -> nothing to contradict.
    silent = _rec("Some Event", description="A fun time for all.", start_date=date(2026, 7, 3))
    assert weekday_contradiction(silent) is False


# --------------------------------------------------------------------------- #
# 4.3 — host extraction from class titles
# --------------------------------------------------------------------------- #
def test_host_from_title_known_instructor() -> None:
    assert _host_from_title("Tai Chi Vince") == "Vince"
    assert _host_from_title("Motion & Mobility Margie") == "Margie"
    assert _host_from_title("Fit & Flex Stephanie") == "Stephanie"


def test_host_from_title_none_when_no_instructor() -> None:
    assert _host_from_title("Farmers Market") is None
    assert _host_from_title("Vince") is None  # single token, not enough remaining
    assert _host_from_title(None) is None


# --------------------------------------------------------------------------- #
# 3.2-field — image_url captured from JSON-LD (regression on existing behaviour)
# --------------------------------------------------------------------------- #
def test_image_url_captured_from_jsonld() -> None:
    html_page = """
    <html><head><script type="application/ld+json">
    {"@type":"Event","name":"Img Show","startDate":"2026-12-03T19:00:00",
     "image":"https://cdn.example.com/poster.jpg"}
    </script></head></html>"""
    recs = parse_jsonld_events(html_page, source="allevents")
    assert recs[0].image_url == "https://cdn.example.com/poster.jpg"
