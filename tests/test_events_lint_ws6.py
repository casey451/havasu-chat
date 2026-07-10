"""WS6 / §14.3 — event-quality lint fixtures (tests-first).

Each real audit defect becomes a machine check, plus precision negatives so the
lint never flags a legitimate row (the cost of a false positive is a needless
review, but we still keep it tight).
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

import pytest

from app.events.lint import (
    category_keyword_contradiction,
    generic_venue_reason,
    is_early_activity,
    is_kids_series,
    is_shouting_title,
    landmark_venue_mismatch,
    lint_event,
    missing_time,
    name_category_contradiction,
    parks_rec_venue_unrecognized,
    reads_as_venue_hours,
    season_out_of_season,
    suspect_ampm_flip,
    suspect_showtime,
    weekday_title_mismatch,
)


# ── AM/PM flip (Glow in the Dark Painting 5:30 AM) ───────────────────────────
@pytest.mark.parametrize("hh,mm,flag", [
    (5, 30, True),   # Glow in the Dark Painting — the §14.3 case
    (5, 15, True),   # Kids Pizza Party Cooking Class — the WS6.3 follow-up case
    (0, 0, True),    # midnight
    (6, 59, True),
    (7, 0, True),    # generalized window now runs to 8 AM (was 7)
    (7, 59, True),
    (8, 0, False),   # 8 AM is the boundary — not flagged
    (9, 0, False),
    (18, 30, False),  # a normal evening event
])
def test_ampm_flip_window(hh: int, mm: int, flag: bool) -> None:
    assert suspect_ampm_flip(time(hh, mm)) is flag


def test_ampm_flip_ignores_24h_and_overnight_and_missing() -> None:
    assert suspect_ampm_flip(time(2, 0), venue_is_24h=True) is False
    assert suspect_ampm_flip(time(2, 0), is_overnight=True) is False
    assert suspect_ampm_flip(time(2, 0), early_ok=True) is False
    assert suspect_ampm_flip(None) is False


# ── movie showtime plausibility (Moana @ Movies Havasu "4 AM") ───────────────
@pytest.mark.parametrize("hh,mm,flag", [
    (4, 0, True),    # the live Moana defect — 4 PM stored as 4 AM
    (0, 0, True),    # midnight
    (8, 59, True),   # anything before 9 AM
    (9, 0, False),   # 9 AM floor — not flagged
    (9, 30, False),  # the legit kids-series floor
    (16, 0, False),  # the corrected afternoon time
])
def test_suspect_showtime_window(hh: int, mm: int, flag: bool) -> None:
    assert suspect_showtime(time(hh, mm)) is flag


def test_suspect_showtime_whitelists_kids_series_and_missing() -> None:
    # A kids-series matinee gets a lower 8 AM floor (whitelisted), but the
    # whitelist is NOT a blanket pass — an absurd 4 AM "kids" show is still caught.
    assert suspect_showtime(time(8, 0), kids_series=True) is False   # 8 AM ok for kids
    assert suspect_showtime(time(8, 30), kids_series=True) is False  # early matinee ok
    assert suspect_showtime(time(4, 0), kids_series=True) is True    # absurd — still flagged
    assert suspect_showtime(time(8, 0), kids_series=False) is True   # 8 AM flagged for non-kids
    assert suspect_showtime(None) is False


def test_is_kids_series_by_title_and_tag() -> None:
    assert is_kids_series("Summer Kids Series") is True
    assert is_kids_series("Kids Club") is True
    assert is_kids_series(tags=["family-series"]) is True
    assert is_kids_series("Moana 2") is False
    assert is_kids_series(None, None) is False


# ── early-activity whitelist (a real pre-dawn start is not a flip) ────────────
@pytest.mark.parametrize("title,venue,early_ok", [
    ("Lap Swim", "Aquatic Center", True),
    ("Sunrise Kayak", "Site Six", True),
    ("Masters Swim", None, True),
    ("Early Bird Boot Camp", "Community Center", True),
    ("Sunrise Yoga", None, True),
    ("Fishing Tournament", "London Bridge Beach", True),
    ("CrossFit Open Gym", None, True),
    ("Havasu Half Marathon", None, True),
    # watersports skew early — inflected forms must match (live-prod false positive)
    ("Adult Intro to Watersports Camp - Paddleboarding Class", None, True),
    ("Kayaking Basics", None, True),
    # not early-legit — a 5 AM start here is a real flip to flag
    ("Kids Pizza Party Cooking Class", "Kitchen", False),
    ("Glow in the Dark Painting", "Community Center", False),
    ("Mexican Train Dominoes", None, False),
])
def test_is_early_activity(title: str, venue: str | None, early_ok: bool) -> None:
    assert is_early_activity(title, venue) is early_ok


def test_whitelisted_early_activity_is_not_ampm_flagged() -> None:
    # A real 5:30 AM lap swim: within the window, but whitelisted → no flag.
    lap = SimpleNamespace(
        title="Lap Swim", description="", start_time=time(5, 30), end_time=time(7, 0),
        location_name="Aquatic Center", source="parks_rec_calendar",
    )
    assert [f.rule for f in lint_event(lap)] == []


# ── venue-hours-as-event (Golf Course — Open daily) ──────────────────────────
@pytest.mark.parametrize("title,flag", [
    ("Golf Course — Bridgewater Links · Open daily", True),
    ("Indoor Golf Simulators — Open 24/7", True),
    ("Toptracer Range · Open 9 AM - 9 PM", True),
    ("Mr. Lucky's Billiards — open 11am to 11pm", True),
    # legitimate events that merely start with "Open"
    ("Open Swim", False),
    ("Open Mic Night", False),
    ("Open House at the Museum", False),
    ("Pickleball Open Play", False),
    ("Family Night Golf", False),
])
def test_reads_as_venue_hours(title: str, flag: bool) -> None:
    assert reads_as_venue_hours(title) is flag


# ── name ↔ category contradiction (Restaurant Consulting under Restaurants) ───
def test_name_category_contradiction_flags_b2b_in_consumer_category() -> None:
    assert name_category_contradiction(
        "Western States Restaurant Consulting", "eat-and-drink/restaurants"
    ) == "consulting"
    assert name_category_contradiction(
        "Desert Wholesale Foods", "eat-and-drink"
    ) == "wholesale"


def test_name_category_contradiction_precision_negatives() -> None:
    # A real restaurant in Restaurants — fine.
    assert name_category_contradiction("Rusty's Restaurant", "restaurants") is None
    # Consulting in a professional category is exactly where it belongs.
    assert name_category_contradiction(
        "Western States Restaurant Consulting", "professional-and-financial"
    ) is None
    assert name_category_contradiction(None, "restaurants") is None
    assert name_category_contradiction("Anything", None) is None


# ── aggregate lint over an event row ─────────────────────────────────────────
def test_lint_event_flags_both_ampm_and_venue_hours() -> None:
    ev = SimpleNamespace(
        title="Bridgewater Links · Open daily",
        description="Come by any time",
        start_time=time(5, 30),
        end_time=None,
    )
    rules = {f.rule for f in lint_event(ev)}
    assert rules == {"ampm_flip", "venue_hours_as_event"}


def test_lint_event_clean_row_has_no_findings() -> None:
    ev = SimpleNamespace(
        title="Popsicles in the Park",
        description="Free popsicles for kids at Rotary Park",
        start_time=time(9, 0),
        end_time=time(11, 0),
    )
    assert lint_event(ev) == []


def test_lint_event_overnight_is_not_ampm_flagged() -> None:
    # A real late show ending after midnight (22:00 -> 01:00) is not a flip.
    ev = SimpleNamespace(
        title="Late Night Comedy", description="", start_time=time(22, 0), end_time=time(1, 0)
    )
    assert lint_event(ev) == []


# ── P&R venue-must-be-a-named-facility ───────────────────────────────────────
@pytest.mark.parametrize("venue,unrecognized", [
    ("Kitchen", True),          # a bare room word — which kitchen?
    ("Room 153", True),         # a room code, no facility
    ("Jane Camlin", True),      # a mis-mapped instructor name
    ("Community Center", False),  # a named facility
    ("Aquatic Center", False),
    ("Wheeler Park", False),
    ("Lake Havasu City Parks & Recreation", False),  # the default venue
    (None, False),              # absent venue is not this rule's concern
    ("", False),
])
def test_parks_rec_venue_unrecognized(venue: str | None, unrecognized: bool) -> None:
    assert parks_rec_venue_unrecognized(venue) is unrecognized


def test_venue_rule_only_applies_to_parks_rec_rows() -> None:
    # A non-P&R event at "Kitchen" (e.g. a cooking demo at a shop) is never
    # venue-checked — "known facility" is a P&R-only concept.
    non_pr = SimpleNamespace(
        title="Knife Skills Demo", description="", start_time=time(18, 0), end_time=None,
        location_name="Kitchen", source="eventbrite", event_url="https://example.com/x",
    )
    assert [f.rule for f in lint_event(non_pr)] == []


def test_kids_pizza_party_cooking_class_trips_both_rules() -> None:
    # Live fixture c765358a: "Kids Pizza Party Cooking Class", 5:15 AM, venue
    # "Kitchen", a P&R flyer row — trips the AM/PM flip AND the venue rule.
    ev = SimpleNamespace(
        title="Kids Pizza Party Cooking Class",
        description="Kids Pizza Party Cooking Class. At Kitchen. For Kids. Cost: $15.",
        start_time=time(5, 15),
        end_time=None,
        location_name="Kitchen",
        source="parks_rec_flyers",
        event_url="https://www.lhcaz.gov/185/Parks-Recreation#cal|2026-07-14|kids-pizza-party-cooking-class|05-15",
    )
    rules = {f.rule for f in lint_event(ev)}
    assert rules == {"ampm_flip", "venue_not_facility"}


# ── landmark venue vs. the real venue in the prose (2026-07-08 re-audit) ───────
def test_landmark_venue_mismatch_flags_placeholder_with_named_venue() -> None:
    # The Bunco case: venue is the shared visitor-center placeholder while the
    # prose names Mudshark Public House.
    assert (
        landmark_venue_mismatch(
            "Go Lake Havasu Visitor Center",
            "Red, White and Blue Bunco Party! Join us at Mudshark Public House.",
        )
        == "Mudshark Public House"
    )


def test_landmark_venue_mismatch_precision_negatives() -> None:
    # A real venue is never flagged, even with an "at <venue>" in the prose.
    assert landmark_venue_mismatch("Mudshark Public House", "Join us at Mudshark Public House.") is None
    # A placeholder whose prose names nothing distinct → no flag (may be a genuine
    # visitor-center event).
    assert landmark_venue_mismatch("Go Lake Havasu Visitor Center", "A fun night out.") is None
    # A placeholder whose prose names the placeholder again → no flag.
    assert (
        landmark_venue_mismatch(
            "Go Lake Havasu Visitor Center", "Meet at the Go Lake Havasu Visitor Center."
        )
        is None
    )


def test_lint_event_flags_landmark_venue_mismatch_on_glh_row() -> None:
    ev = SimpleNamespace(
        title="Red, White and Blue Bunco Party",
        description="A patriotic Bunco night. Join us at Mudshark Public House.",
        start_time=time(18, 0),
        end_time=None,
        location_name="Go Lake Havasu Visitor Center",
        source="go_lake_havasu",
        event_url="https://www.golakehavasu.com/event/bunco",
    )
    rules = {f.rule for f in lint_event(ev)}
    assert "landmark_venue_mismatch" in rules


# ── weekday-in-title mismatch (pre-launch deep-verify battery) ────────────────
@pytest.mark.parametrize("title,d,flag", [
    ("Taco Tuesday", date(2026, 7, 14), False),   # 2026-07-14 IS a Tuesday — fine
    ("Taco Tuesday", date(2026, 7, 15), True),    # a Wednesday — mismatch
    ("Monday Night Trivia", date(2026, 7, 14), True),   # Tuesday
    ("First Friday Art Walk", date(2026, 7, 3), False),  # 2026-07-03 IS a Friday
    ("First Friday Art Walk", date(2026, 7, 4), True),   # a Saturday
    ("Saturdays at the Market", date(2026, 7, 11), False),  # Saturday
    # ambiguous / no single day → never flagged
    ("Mon/Wed/Fri Bootcamp", date(2026, 7, 14), False),
    ("Yoga Monday & Thursday", date(2026, 7, 15), False),
    ("Summer Concert Series", date(2026, 7, 15), False),
])
def test_weekday_title_mismatch(title: str, d: object, flag: bool) -> None:
    assert (weekday_title_mismatch(title, d) is not None) is flag


def test_weekday_title_mismatch_guards() -> None:
    assert weekday_title_mismatch(None, date(2026, 7, 14)) is None
    assert weekday_title_mismatch("Taco Tuesday", None) is None


# ── season / holiday out of season ───────────────────────────────────────────
@pytest.mark.parametrize("title,d,flag", [
    ("Summer Concert Series", date(2026, 7, 15), False),   # July is summer
    ("Summer Concert Series", date(2026, 12, 15), True),   # December is not
    ("Halloween Spooktacular", date(2026, 10, 20), False),
    ("Halloween Spooktacular", date(2026, 7, 20), True),   # July Halloween — wrong
    ("Christmas Market", date(2026, 4, 5), True),          # April Christmas — wrong
    ("Winter Wonderland", date(2026, 1, 5), False),        # January is winter
    ("4th of July Parade", date(2026, 7, 4), False),
    ("4th of July Parade", date(2026, 9, 4), True),
    # deliberate cross-season theme — title names the actual month → not flagged
    ("Christmas in July Camp", date(2026, 7, 14), False),
    ("Christmas Market", date(2026, 12, 5), False),
    # precision: season words embedded in names/venues are not flagged
    ("Springboard Diving Lessons", date(2026, 7, 1), False),
    ("Waterfall Hike", date(2026, 7, 1), False),
])
def test_season_out_of_season(title: str, d: object, flag: bool) -> None:
    assert (season_out_of_season(title, d) is not None) is flag


# ── generic / address venue ──────────────────────────────────────────────────
@pytest.mark.parametrize("venue,flag", [
    ("2144 McCulloch Blvd N", True),           # bare street address
    ("1350 McCulloch Blvd S, Lake Havasu City", True),
    ("TBD", True),
    ("Online", True),
    ("Various Locations", True),
    # named places / districts — not flagged
    ("Lake Havasu City Aquatic Center", False),
    ("Downtown Lake Havasu", False),
    ("Mudshark Public House", False),
    ("The KAWS", False),
    (None, False),
    ("", False),
])
def test_generic_venue_reason(venue: str | None, flag: bool) -> None:
    assert (generic_venue_reason(venue) is not None) is flag


# ── missing time ─────────────────────────────────────────────────────────────
def test_missing_time() -> None:
    assert missing_time(None) is True
    assert missing_time(None, all_day=True) is False
    assert missing_time(time(9, 0)) is False


# ── ALL-CAPS shouting title ──────────────────────────────────────────────────
@pytest.mark.parametrize("title,flag", [
    ("SUMMER BLOWOUT SALE", True),
    ("GLOW IN THE DARK PARTY", True),
    ("BINGO NIGHT", True),
    # brands/acronyms with <2 long-caps words — not flagged
    ("USA BMX Race", False),
    ("Summer Blowout Sale", False),
    ("Live Music at The Foundry", False),
    ("VBS Kickoff", False),
    (None, False),
])
def test_is_shouting_title(title: str | None, flag: bool) -> None:
    assert is_shouting_title(title) is flag


# ── category ↔ title-keyword contradiction (shark → boating) ─────────────────
def test_category_keyword_contradiction() -> None:
    assert category_keyword_contradiction("Shark Week Splash", "Things to Do,boating") is not None
    assert category_keyword_contradiction("Sunset Yoga", "Eat & Drink") is not None
    assert category_keyword_contradiction("Kids Wine & Paint", "Family,kids") is not None
    # precision negatives
    assert category_keyword_contradiction("Shark Week Splash", "Family,kids") is None
    assert category_keyword_contradiction("Sunset Yoga", "Fitness & Sports,yoga") is None
    assert category_keyword_contradiction("Wine Walk", "Eat & Drink,wine") is None
    assert category_keyword_contradiction(None, "boating") is None


# ── new rules never fire on a legitimate, fully-populated row ─────────────────
def test_new_rules_precision_on_clean_populated_event() -> None:
    ev = SimpleNamespace(
        title="Lake Havasu Farmers Market",
        description="A community market downtown.",
        start_time=time(8, 0),
        end_time=time(12, 0),
        location_name="Downtown Lake Havasu",
        date=date(2026, 7, 11),        # a Saturday
        category="Things to Do,market",
        source="allevents",
        event_url="https://www.lakehavasufarmersmarket.com/",
    )
    assert lint_event(ev) == []
