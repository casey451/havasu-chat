"""Unit tests for the Lake Havasu Senior Center collector + Seniors filter."""

from __future__ import annotations

from datetime import date, time

from app.events import senior_center as sc
from app.events.senior_filter import is_senior_event

_TODAY = date(2026, 6, 19)


def test_recurring_specs_cover_lunch_and_activities():
    specs = sc.recurring_specs()
    assert len(specs) == 1 + len(sc.RECURRING_ACTIVITIES)
    titles = {s.title for s in specs}
    assert "Community Lunch (Meals on Wheels)" in titles
    assert {"Qigong Tai Chi", "Hand & Foot", "Laughing Yoga", "Bunco"} <= titles


def test_every_recurring_spec_is_tagged_and_recurring():
    for s in sc.recurring_specs():
        assert s.is_recurring is True
        assert s.rrule and s.rrule.startswith("FREQ=WEEKLY;BYDAY=")
        assert "senior" in [t.lower() for t in s.tags]


def test_schedule_matches_published_days():
    by_title = {a.title: a for a in sc.RECURRING_ACTIVITIES}
    # Corrections verified against the June 2026 Weekly Activities Calendar.
    assert by_title["Party Bridge"].byday == ("TU", "TH")
    assert by_title["Pinochle"].byday == ("WE", "FR")
    assert by_title["Hand & Foot"].byday == ("TU",)
    assert by_title["Laughing Yoga"].byday == ("WE",)
    assert by_title["Bunco"].byday == ("TH",)
    assert by_title["Qigong Tai Chi"].start == time(12, 0)


def test_anchor_date_is_a_real_occurrence_weekday():
    assert sc.anchor_date(("FR",)).weekday() == 4
    assert sc.anchor_date(("MO", "WE", "FR")).weekday() == 0
    assert sc.anchor_date(("TU", "TH")).weekday() == 1  # earliest weekday


def test_rrule_for_byday():
    assert sc.rrule_for(("MO", "WE", "FR")) == "FREQ=WEEKLY;BYDAY=MO,WE,FR"


def test_curated_specials_future_only_and_tagged():
    specs = sc.curated_special_specs(today=_TODAY)
    titles = {s.title for s in specs}
    assert "Christmas in July" in titles
    assert "Celebrate Our Seniors: Ice Cream Social" in titles
    for s in specs:
        assert s.is_recurring is False
        assert "senior" in s.tags
    # A special whose last day has passed is dropped.
    assert sc.curated_special_specs(today=date(2026, 12, 1)) == []


_FIXTURE_HTML = """
<h1>Tai Chi Qigong Classes</h1><h2>Every Friday, 12:00 PM</h2>
<h1>Stronger Together Seminar</h1>
<h2>"Building a Safer Future for Seniors"</h2>
<h2>Tuesday, June 9, 2026 12:00 PM &#8211; 2:00 PM</h2>
<h2>Lake Havasu Senior Center, 450 Acoma Blvd S</h2>
<h2>Upcoming Events</h2>
"""


def test_parse_special_events_extracts_dated_seminar():
    specials = sc.parse_special_events(_FIXTURE_HTML)
    june9 = [s for s in specials if s.date == date(2026, 6, 9)]
    assert len(june9) == 1
    ev = june9[0]
    assert ev.title == "Stronger Together Seminar"
    assert ev.start_time == time(12, 0)
    assert ev.end_time == time(14, 0)
    assert "senior" in ev.tags


def test_parse_special_events_skips_recurring_and_sections():
    titles = {s.title.lower() for s in sc.parse_special_events(_FIXTURE_HTML)}
    assert "tai chi qigong classes" not in titles
    assert "upcoming events" not in titles


def test_collect_merges_recurring_curated_and_specials():
    specs = sc.collect(html=_FIXTURE_HTML, today=_TODAY)
    assert any(s.title == "Qigong Tai Chi" and s.is_recurring for s in specs)
    assert any(s.title == "Christmas in July" for s in specs)
    assert any(s.title == "Stronger Together Seminar" for s in specs)


def test_collect_offline_still_returns_recurring_and_curated():
    specs = sc.collect(html="", today=_TODAY)
    expected = len(sc.recurring_specs()) + len(sc.curated_special_specs(today=_TODAY))
    assert len(specs) == expected


def test_is_senior_event_by_tag_and_venue_only():
    # Phase 4 / Q5 (Casey 2026-06-26): gate by TAG or Senior-Center VENUE only,
    # never a title keyword.
    assert is_senior_event("Bunco", ["senior"]) is True
    assert is_senior_event("Meals on Wheels Volunteer Day", ["meals on wheels"]) is True
    assert is_senior_event("Generic Class", None, "Lake Havasu Senior Center") is True
    # "Senior" in the title alone no longer gates — needs the tag or senior venue.
    assert is_senior_event("Senior Exercise Class", None) is False
    assert is_senior_event("Live Music at the Brewery", ["music"]) is False
