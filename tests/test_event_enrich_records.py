"""Detail-page enrichment of time/venue + live-music tagging (A-Z band fix)."""

from __future__ import annotations

from datetime import date, time

from app.contrib.event_enrich import (
    best_venue_name,
    enrich_event_records,
    record_from_detail_html,
)
from app.contrib.event_ingest import _live_music_tags, _tags
from app.contrib.event_record import EventRecord

# A trimmed AllEvents-style detail page: a band gig at a lounge, 7pm start,
# location is a bare street address, organizer is the real venue.
_AZ_HTML = """<html><head>
<script type="application/ld+json">
{"@type":"Event","name":"A-Z",
 "startDate":"2026-06-18T19:00:00-07:00","endDate":"2026-06-18T22:00:00-07:00",
 "location":{"@type":"Place","name":"317 S Lake Havasu Ave",
   "address":{"@type":"PostalAddress","streetAddress":"317 Lake Havasu Ave S","addressLocality":"Lake Havasu City","addressRegion":"AZ"}},
 "organizer":[{"@type":"Organization","name":"Lighthouse Lounge"}],
 "description":"Based in Lake Havasu City, A-Z brings a massive setlist of Classic Rock and Country hits to the local stage. This dynamic duo knows how to get everyone singing along."}
</script></head><body></body></html>"""


def _thin_az() -> EventRecord:
    # what the index scrape produces: right date, midnight time, city venue, no body
    return EventRecord(
        source="allevents", title="A-Z", start_date=date(2026, 6, 18),
        start_time=time(0, 0), venue_name="Lake Havasu City",
        url="https://allevents.in/lake-havasu-city/a-z/200030130283746", description="",
    )


def test_enrichment_recovers_time_venue_and_description() -> None:
    rec = _thin_az()
    n = enrich_event_records([rec], fetch_text=lambda u: _AZ_HTML, source="allevents")
    assert n == 1
    assert rec.start_time == time(19, 0)          # the real 7pm, not midnight
    assert rec.end_time == time(22, 0)
    assert rec.venue_name == "Lighthouse Lounge"  # organizer, not the street address
    assert "setlist" in (rec.description or "").lower()


def test_enrichment_does_not_overwrite_a_real_time() -> None:
    rec = _thin_az()
    rec.start_time = time(18, 30)  # index already had a real time
    enrich_event_records([rec], fetch_text=lambda u: _AZ_HTML, source="allevents")
    assert rec.start_time == time(18, 30)  # preserved


def test_enriched_band_event_gets_music_tag() -> None:
    rec = _thin_az()
    enrich_event_records([rec], fetch_text=lambda u: _AZ_HTML, source="allevents")
    assert "music" in _tags(rec)  # -> "Music & nightlife" lane


def test_music_tag_from_venue_alone() -> None:
    rec = EventRecord(source="x", title="A-Z", start_date=date(2026, 6, 18),
                      start_time=time(19, 0), venue_name="Lighthouse Lounge", description="")
    assert _live_music_tags(rec) == ["music"]


def test_civic_event_never_tagged_music() -> None:
    rec = EventRecord(source="x", title="City Council Meeting", start_date=date(2026, 6, 18),
                      start_time=time(18, 0), venue_name="City Hall",
                      description="Council DJ adjustments and band-width budget review.")
    assert _live_music_tags(rec) == []
    assert "music" not in _tags(rec)


def test_non_music_event_not_tagged() -> None:
    rec = EventRecord(source="x", title="Farmers Market", start_date=date(2026, 6, 18),
                      start_time=time(8, 0), venue_name="McCulloch Blvd",
                      description="Fresh local produce and crafts every Saturday morning.")
    assert _live_music_tags(rec) == []


def test_best_venue_prefers_real_name_over_street_address() -> None:
    assert best_venue_name("317 S Lake Havasu Ave", "Lighthouse Lounge") == "Lighthouse Lounge"
    assert best_venue_name("Lighthouse Lounge", "Some Promoter LLC") == "Lighthouse Lounge"
    assert best_venue_name("", "Lighthouse Lounge") == "Lighthouse Lounge"


def test_record_from_detail_html_none_when_no_jsonld() -> None:
    assert record_from_detail_html("<html><body>no jsonld</body></html>", source="x") is None
