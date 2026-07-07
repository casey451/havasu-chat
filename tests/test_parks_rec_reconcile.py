"""WS6b Phase 1 — flyer↔WebTrac reconciler (pure matching + classification)."""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from typing import Any

import pytest

from app.contrib import parks_rec_reconcile as pr
from app.events.lint import lint_event


def _ev(title: str, d: date, t: time | None, venue: str | None = None, id: str = "x") -> Any:
    return SimpleNamespace(
        id=id, title=title, date=d, start_time=t, end_time=None,
        location_name=venue, description="", source="parks_rec_flyers",
        event_url="https://www.lhcaz.gov/185/Parks-Recreation#cal|x",
    )


def _webtrac(title: str, d: date, t: time | None, venue: str | None = None, id: str = "w") -> Any:
    return SimpleNamespace(
        id=id, title=title, date=d, start_time=t, end_time=None,
        location_name=venue, description="", source="parks_rec_webtrac",
        event_url="https://register.lhcaz.gov/webtrac/iteminfo?FMID=1",
    )


# ── title similarity ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("a,b,similar", [
    ("Glow in the Dark Family Painting", "Glow in the Dark Family Painting", True),
    ("Kids Pizza Party", "Kids Pizza Party Cooking Class", True),   # prefix
    ("Tiny Tots (Ages 2-3)", "Tiny Tots", True),                    # parens stripped
    ("Adult Watercolor Workshop", "Watercolor Workshop Adult", True),  # token jaccard
    ("Line Dancing", "Ballroom Dancing", False),                    # one shared token
    ("Yoga", "Pilates", False),
    ("", "Anything", False),
])
def test_titles_similar(a: str, b: str, similar: bool) -> None:
    assert pr.titles_similar(a, b) is similar


# ── venue (soft) ──────────────────────────────────────────────────────────────
def test_venue_compatible() -> None:
    assert pr.venue_compatible("Aquatic Center", "Aquatic Center pool") is True
    assert pr.venue_compatible("Kitchen", None) is True            # missing → no contradiction
    assert pr.venue_compatible(None, "Wheeler Park") is True
    assert pr.venue_compatible("Lake Havasu City Parks & Recreation", "Wheeler Park") is True
    assert pr.venue_compatible("Wheeler Park", "Rotary Community Park") is False


# ── time conflict shape ───────────────────────────────────────────────────────
def test_time_delta_and_flip() -> None:
    assert pr.time_delta_minutes(time(17, 0), time(17, 30)) == 30
    assert pr.time_delta_minutes(time(17, 0), None) is None
    # 5:30 AM vs 5:30 PM — same clock, different meridiem → a correctable flip.
    assert pr.looks_like_ampm_flip(time(5, 30), time(17, 30)) is True
    # 5:00 PM vs 5:30 PM — not a flip, just a disagreement.
    assert pr.looks_like_ampm_flip(time(17, 30), time(17, 0)) is False


# ── matching ──────────────────────────────────────────────────────────────────
def test_match_prefers_exact_date() -> None:
    flyer = _ev("Tiny Tots", date(2026, 7, 14), time(10, 0))
    wts = [
        _webtrac("Tiny Tots", date(2026, 7, 13), time(10, 0), id="near"),
        _webtrac("Tiny Tots", date(2026, 7, 14), time(10, 0), id="exact"),
    ]
    assert pr.match_flyer(flyer, wts).id == "exact"


def test_match_allows_unambiguous_off_by_one() -> None:
    # The grid off-by-one: flyer Tue, WebTrac Wed, single candidate → match.
    flyer = _ev("Creative Mondays Mosaic", date(2026, 7, 13), time(15, 0))
    wts = [_webtrac("Creative Mondays Mosaic", date(2026, 7, 14), time(15, 0), id="wed")]
    assert pr.match_flyer(flyer, wts).id == "wed"


def test_match_refuses_ambiguous_recurring_series() -> None:
    # A weekly class: two nearby WebTrac dates, no exact flyer-date hit → refuse.
    flyer = _ev("Line Dancing", date(2026, 7, 8), time(10, 0))
    wts = [
        _webtrac("Line Dancing", date(2026, 7, 7), time(10, 0), id="a"),
        _webtrac("Line Dancing", date(2026, 7, 9), time(10, 0), id="b"),
    ]
    assert pr.match_flyer(flyer, wts) is None


def test_match_none_when_no_similar_title() -> None:
    flyer = _ev("Underwater Basket Weaving", date(2026, 7, 14), time(10, 0))
    assert pr.match_flyer(flyer, [_webtrac("Yoga", date(2026, 7, 14), time(10, 0))]) is None


def test_match_never_pairs_an_event_with_itself() -> None:
    # Regression (2026-07-07 self-match mis-retire): a WebTrac event whose combined
    # source also names the flyer source lands in BOTH sets. It must never match /
    # supersede itself (same id), which would retire the authoritative row.
    ev = _webtrac("Kids Pizza Party Cooking Class", date(2026, 7, 8), time(17, 15), id="same")
    assert pr.match_flyer(ev, [ev]) is None
    v = pr.classify_flyer(ev, [ev], lint_fn=lint_event)
    assert v.action != pr.SUPERSEDE  # not superseded against itself


def test_is_webtrac_event() -> None:
    assert pr.is_webtrac_event(_webtrac("X", date(2026, 7, 8), time(9, 0))) is True
    assert pr.is_webtrac_event(_ev("X", date(2026, 7, 8), time(9, 0))) is False
    assert pr.is_webtrac_event(SimpleNamespace(event_url=None)) is False


# ── classification ────────────────────────────────────────────────────────────
def test_supersede_when_times_agree() -> None:
    flyer = _ev("Tiny Tots", date(2026, 7, 14), time(10, 0), venue="Kitchen")
    wts = [_webtrac("Tiny Tots", date(2026, 7, 14), time(10, 5), venue="Community Center")]
    v = pr.classify_flyer(flyer, wts, lint_fn=lint_event)
    assert v.action == pr.SUPERSEDE
    assert v.webtrac is wts[0]


def test_supersede_when_webtrac_corrects_ampm_flip() -> None:
    flyer = _ev("Kids Pizza Party Cooking Class", date(2026, 7, 14), time(5, 15), venue="Kitchen")
    wts = [_webtrac("Kids Pizza Party Cooking Class", date(2026, 7, 14), time(17, 15))]
    v = pr.classify_flyer(flyer, wts, lint_fn=lint_event)
    assert v.action == pr.SUPERSEDE
    assert "webtrac-corrects-ampm-flip" in v.reasons


def test_glow_time_conflict_needs_human_confirmation() -> None:
    # The open data question: WebTrac 5:00 PM vs flyer 5:30 PM — both plausible,
    # not a flip. Never assume either; flag for a human to confirm with P&R.
    flyer = _ev("Glow in the Dark Family Painting", date(2026, 7, 8), time(17, 30))
    wts = [_webtrac("Glow in the Dark Family Painting", date(2026, 7, 8), time(17, 0))]
    v = pr.classify_flyer(flyer, wts, lint_fn=lint_event)
    assert v.action == pr.NEEDS_CONFIRMATION
    assert v.time_delta_minutes == 30
    assert "time-conflict" in v.reasons


def test_quarantine_flyer_only_that_fails_lint() -> None:
    # No WebTrac twin + a lint failure (venue-hours-as-event) → quarantine.
    flyer = _ev("Golf Course — Bridgewater Links · Open daily", date(2026, 7, 14), time(9, 0))
    v = pr.classify_flyer(flyer, [], lint_fn=lint_event)
    assert v.action == pr.QUARANTINE
    assert "venue_hours_as_event" in v.reasons


def test_keep_clean_flyer_only_residue() -> None:
    flyer = _ev("Free Summer Craft Series", date(2026, 7, 14), time(10, 0), venue="Wheeler Park")
    v = pr.classify_flyer(flyer, [], lint_fn=lint_event)
    assert v.action == pr.KEEP
    assert v.reasons == ()


def test_reconcile_aggregate_counts() -> None:
    flyers = [
        _ev("Tiny Tots", date(2026, 7, 14), time(10, 0)),                       # supersede
        _ev("Glow in the Dark Family Painting", date(2026, 7, 8), time(17, 30)),  # needs_conf
        _ev("Open 24/7 Simulators", date(2026, 7, 14), time(9, 0)),            # quarantine
        _ev("Free Craft Series", date(2026, 7, 14), time(10, 0), venue="Wheeler Park"),  # keep
    ]
    wts = [
        _webtrac("Tiny Tots", date(2026, 7, 14), time(10, 0)),
        _webtrac("Glow in the Dark Family Painting", date(2026, 7, 8), time(17, 0)),
    ]
    result = pr.reconcile(flyers, wts, lint_fn=lint_event)
    assert result.counts == {
        pr.SUPERSEDE: 1, pr.NEEDS_CONFIRMATION: 1, pr.QUARANTINE: 1, pr.KEEP: 1
    }
