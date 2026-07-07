"""WS6 / §14.3 — event-quality lint fixtures (tests-first).

Each real audit defect becomes a machine check, plus precision negatives so the
lint never flags a legitimate row (the cost of a false positive is a needless
review, but we still keep it tight).
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace

import pytest

from app.events.lint import (
    lint_event,
    name_category_contradiction,
    reads_as_venue_hours,
    suspect_ampm_flip,
)


# ── AM/PM flip (Glow in the Dark Painting 5:30 AM) ───────────────────────────
@pytest.mark.parametrize("hh,mm,flag", [
    (5, 30, True),   # Glow in the Dark Painting — the §14.3 case
    (0, 0, True),    # midnight
    (6, 59, True),
    (7, 0, False),   # 7 AM is the boundary — not flagged
    (9, 0, False),
    (18, 30, False),  # a normal evening event
])
def test_ampm_flip_window(hh: int, mm: int, flag: bool) -> None:
    assert suspect_ampm_flip(time(hh, mm)) is flag


def test_ampm_flip_ignores_24h_and_overnight_and_missing() -> None:
    assert suspect_ampm_flip(time(2, 0), venue_is_24h=True) is False
    assert suspect_ampm_flip(time(2, 0), is_overnight=True) is False
    assert suspect_ampm_flip(None) is False


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
