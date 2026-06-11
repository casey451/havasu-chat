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
    ("Wine & Watercolor with KJ", None, "Wine & Watercolor"),
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
