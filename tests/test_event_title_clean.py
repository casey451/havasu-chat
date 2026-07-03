"""clean_event_title (fixlist §2.3) — pins the exact junk visible on the live
home calendar, plus guards that real titles are preserved and output is never
empty. Render-time only: stored Event.title is untouched."""

from __future__ import annotations

import pytest

from app.events.title_clean import clean_event_title

CASES = [
    # (raw, location_name, expected)
    ("Fit & Flex (155) Stephanie", None, "Fit & Flex"),
    ("Motion & Mobility Margie", None, "Motion & Mobility"),
    ("Tai Chi Vince", None, "Tai Chi"),
    ("Aqua Challenge Vince", None, "Aqua Challenge"),
    ("Aqua Aerobics Margie", None, "Aqua Aerobics"),
    ("Pickleball Round Robin June 25", None, "Pickleball Round Robin"),
    ("Baby Sitting Class June 6", None, "Baby Sitting Class"),
    (
        "Free Family Swim Sponsored by: Abundant Grace Church Event is limited to "
        "the first 400 people",
        None,
        "Free Family Swim",
    ),
    ("9 AM Beginner Pilates (Wed/Fri)", None, "Beginner Pilates"),
    ("Inferno (6 AM)", None, "Inferno"),
    ("Rec Gym (Wed 4 PM)", None, "Rec Gym"),
    ("Rowdy Bingo at Grapes N Grains", "Grapes N Grains", "Rowdy Bingo"),
    # §6 separator-form venue echoes: the venue is already shown beside the
    # title, so a trailing "— Venue" / "· Venue" / "- Venue" is redundant.
    ("Golf Course — Lake Havasu Golf Club", "Lake Havasu Golf Club", "Golf Course"),
    ("Indoor Golf Simulators — Back Nine Golf", "Back Nine Golf", "Indoor Golf Simulators"),
    (
        "Universal Sonics Gymnastics & Cheer · Universal Sonics",
        "Universal Sonics",
        "Universal Sonics Gymnastics & Cheer",
    ),
    # Venue embedded mid-title (not a trailing echo) is preserved.
    ("Live at Back Nine Golf Tonight", "Back Nine Golf", "Live at Back Nine Golf Tonight"),
    ("Wine & Watercolor with KJ", None, "Wine & Watercolor"),
    # Instructor-suffix coverage for every observed name (2.4):
    ("Aqua Aerobics Renae", None, "Aqua Aerobics"),
    ("Deep Water Danica", None, "Deep Water"),
    # Long trailing date baked into the title (weekday + month + ordinal + year
    # + bang) is dropped; internal "at <venue>" prose is preserved (2.4):
    (
        "Crosscutt Live at the Naked Turtle at Nautical Beach Resort "
        "Friday June 12th 2026!",
        None,
        "Crosscutt Live at the Naked Turtle at Nautical Beach Resort",
    ),
    ("Summer Concert Saturday July 4th 2026", None, "Summer Concert"),
    ("Trivia Night Friday June 12th", None, "Trivia Night"),
    # Preserved — no junk to strip:
    ("Creative Mondays - felt crafts", None, "Creative Mondays - felt crafts"),
    ("Open Swim", None, "Open Swim"),
    ("HAVASIS DINE & DONATE", None, "HAVASIS DINE & DONATE"),
    ("Sunrise Kayaking", None, "Sunrise Kayaking"),
]


@pytest.mark.parametrize("raw,loc,expected", CASES)
def test_clean_event_title(raw, loc, expected):
    assert clean_event_title(raw, location_name=loc) == expected


def test_idempotent():
    for raw, loc, _ in CASES:
        once = clean_event_title(raw, location_name=loc)
        assert clean_event_title(once, location_name=loc) == once


def test_never_empty_falls_back_to_original():
    # An all-junk title must not collapse to "" — return the original instead.
    assert clean_event_title("Sponsored by Acme Corp") == "Sponsored by Acme Corp"
    assert clean_event_title("") == ""
    assert clean_event_title(None) == ""


def test_does_not_strip_unknown_trailing_name():
    # Only curated instructor names are stripped; a real trailing word stays.
    assert clean_event_title("Concert featuring Beethoven") == "Concert featuring Beethoven"
    assert clean_event_title("Lecture by Professor Smith") == "Lecture by Professor Smith"


def test_all_observed_instructor_names_are_covered():
    # 2.4: the structured-host lane reads INSTRUCTOR_NAMES from this module, so
    # every observed name must be present and stripped as a trailing suffix.
    from app.events.title_clean import INSTRUCTOR_NAMES

    for name in ("margie", "vince", "stephanie", "kj", "renae", "danica"):
        assert name in INSTRUCTOR_NAMES
        stripped = clean_event_title(f"Aqua Class {name.capitalize()}")
        assert stripped == "Aqua Class"


def test_instructor_only_title_never_empties():
    # A lone instructor name (no other word) must not collapse to "" — the
    # >= 2-word guard keeps the original.
    assert clean_event_title("Margie") == "Margie"


def test_clean_venue_label_strips_trailing_address():
    from app.events.title_clean import clean_venue_label

    # "Name + address" -> just the name.
    assert clean_venue_label("Rotary Park 1400 S. Smoketree Ave. Lake Havasu City, AZ. 86403") == "Rotary Park"
    assert clean_venue_label("Star Cinemas 5601 Highway 95, Lake Havasu City") == "Star Cinemas"
    assert clean_venue_label(
        "Lake Havasu City Aquatic Center, 100 Park Avenue, Room 153/154, Lake Havasu City, AZ 86403"
    ) == "Lake Havasu City Aquatic Center"
    assert clean_venue_label("Mohave College, 1977 Acoma Blvd West, Room 600") == "Mohave College"
    # Clean names are untouched — incl. a comma+word and a small number.
    assert clean_venue_label("Elite Martial Arts, Inc.") == "Elite Martial Arts, Inc."
    assert clean_venue_label("Iron Wolf Golf & Country Club") == "Iron Wolf Golf & Country Club"
    assert clean_venue_label("Pier 66") == "Pier 66"
    assert clean_venue_label(None) is None


def test_clean_venue_label_names_known_bare_addresses():
    from app.events.title_clean import clean_venue_label

    # Known bare-address venues get their real name (verified 2026-06-23), incl.
    # a second source's same-address label so the feeds read consistently.
    assert clean_venue_label("2134 McCulloch Blvd N. in beautiful Lake Havasu City") == "Havasu Lanes"
    assert clean_venue_label("2146 McCulloch Blvd") == "GraceArts Live"
    assert clean_venue_label("2144 McCulloch Blvd N Lake Havasu City, AZ 86403") == "Downtown Lake Havasu"


def test_clean_venue_label_fixes_known_misspelling():
    from app.events.title_clean import clean_venue_label

    # "Roatary" -> "Rotary" (Splash Bash venue typo from the scrape). Whole-word,
    # case-insensitive, and only the misspelling — the rest of the label is kept.
    assert clean_venue_label("Roatary Community Ball Fields") == "Rotary Community Ball Fields"
    assert clean_venue_label("ROATARY PARK") == "Rotary PARK"
    # A correctly-spelled name is never touched.
    assert clean_venue_label("Rotary Park") == "Rotary Park"
    assert clean_venue_label("3516 McCulloch Blvd N, Lake Havasu City, AZ 86406") == "Abundant Grace Church"
