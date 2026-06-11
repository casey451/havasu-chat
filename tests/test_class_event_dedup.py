"""Class-occurrence dedup — normalized-token matching + schedule-twin collapse.

Regression suite for the 2026-06-10 live bug where /events-ui showed every
Aquatic Center class twice (a dated Event row like "Motion & Mobility Margie"
AND a "Runs regularly ↻" Schedule row "Motion & Mobility") and every Havasu
Pilates slot twice (two Schedule rows with title variants). The old contract
matched exact (lowercased title, date) only.

Known honest miss (documented, not asserted away): "Arthritis Class Vince"
(event) vs "Arthritis Water Class" (schedule) — token sets {arthritis, class,
vince} / {arthritis, water, class} are not subset-related. That pair needs the
Schedule-side data cleanup, not looser matching.
"""

from __future__ import annotations

from datetime import date, time

from app.events.class_occurrences import (
    ClassOccurrence,
    _drop_schedule_twins,
    drop_event_duplicates,
)

D = date(2026, 6, 10)


def occ(
    title: str,
    hour: int | None,
    minute: int = 0,
    *,
    venue: str = "Lake Havasu City Aquatic Center",
    slug: str | None = "lake-havasu-city-aquatic-center",
    weekdays: frozenset[int] = frozenset({2}),
) -> ClassOccurrence:
    return ClassOccurrence(
        title=title,
        date=D,
        start_time=time(hour, minute) if hour is not None else None,
        end_time=None,
        venue=venue,
        provider_slug=slug,
        weekdays=weekdays,
    )


# --- drop_event_duplicates ---------------------------------------------------

def test_instructor_suffixed_event_suppresses_schedule_twin():
    keys = {("motion & mobility margie", D, time(8, 0))}
    assert drop_event_duplicates([occ("Motion & Mobility", 8)], keys) == []


def test_parenthetical_schedule_variant_is_suppressed():
    keys = {("tai chi vince", D, time(8, 0))}
    assert drop_event_duplicates([occ("Tai Chi (Aquatic)", 8)], keys) == []


def test_time_window_keeps_distinct_sessions_apart():
    keys = {("lap swim", D, time(5, 0))}
    kept = drop_event_duplicates(
        [occ("Lap Swim (Morning)", 5), occ("Lap Swim (Evening)", 17)], keys
    )
    assert [o.title for o in kept] == ["Lap Swim (Evening)"]


def test_numeric_parenthetical_junk_is_ignored_in_matching():
    keys = {("fit & flex (155) stephanie", D, time(9, 0))}
    assert drop_event_duplicates([occ("Fit & Flex", 9)], keys) == []


def test_unrelated_titles_survive():
    keys = {("swim meet", D, time(17, 0))}
    kept = drop_event_duplicates([occ("Swim League", 17)], keys)
    assert [o.title for o in kept] == ["Swim League"]


def test_legacy_two_tuple_keys_still_supported():
    # Old callers passed (title, date) — missing time is a wildcard, matching
    # the old behavior of dropping on title+date alone.
    kept = drop_event_duplicates([occ("Lap Swim (Evening)", 17)], {("lap swim", D)})
    assert kept == []


def test_exact_match_still_drops():
    keys = {("open swim", D, time(12, 0))}
    assert drop_event_duplicates([occ("Open Swim", 12)], keys) == []


# --- _drop_schedule_twins ------------------------------------------------------

def test_pilates_title_variants_collapse_to_one():
    rows = [
        occ("9:00 AM Beginner Pilates (Wed/Fri)", 9, venue="Havasu Pilates Studio", slug=None),
        occ("Beginner Reformer Pilates - 9:00 AM Wed/Fri", 9, venue="Havasu Pilates Studio", slug=None),
    ]
    kept = _drop_schedule_twins(rows)
    assert len(kept) == 1
    # The more specific title (more tokens) wins.
    assert kept[0].title == "Beginner Reformer Pilates - 9:00 AM Wed/Fri"


def test_same_tokens_different_clock_stay_separate():
    rows = [
        occ("Adult No-Gi (Morning)", 6, venue="Bridge City Combat", slug="bridge-city-combat"),
        occ("Adult No-Gi (Night)", 19, 15, venue="Bridge City Combat", slug="bridge-city-combat"),
    ]
    assert len(_drop_schedule_twins(rows)) == 2


def test_same_title_different_venue_stays_separate():
    rows = [
        occ("Beginner Pilates", 9, venue="Havasu Pilates Studio", slug=None),
        occ("Beginner Pilates", 9, venue="Some Other Studio", slug=None),
    ]
    assert len(_drop_schedule_twins(rows)) == 2


def test_distinct_classes_same_venue_survive():
    rows = [
        occ("Rec Gym (Wed 4 PM)", 16, venue="Universal Sonics", slug="universal-sonics"),
        occ("Tiny Tumblers (Wed)", 17, 30, venue="Universal Sonics", slug="universal-sonics"),
    ]
    assert len(_drop_schedule_twins(rows)) == 2


# --- url fallback ---------------------------------------------------------------

def test_slugless_class_has_no_link_instead_of_self_link():
    o = occ("Beginner Pilates", 9, venue="Havasu Pilates Studio", slug=None)
    assert o.url == ""  # template renders a non-link row


def test_slugged_class_links_to_venue():
    o = occ("Lap Swim", 5)
    assert o.url == "/provider/lake-havasu-city-aquatic-center"
