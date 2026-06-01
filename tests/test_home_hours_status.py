"""Unit tests for ``app.home.queries._hours_status`` (PR 1 - C9 acceptance).

The status pill state machine is one of the C9 acceptance bullets in
``CRITIQUE_AND_REDESIGN.md``: never show a pill we can't justify with
data. ``_hours_status`` returns ``("unknown", "Hours on profile")``
for that no-data branch; the template renders plain text instead of a
pill when the class is ``unknown``.

These tests use a minimal stub provider (only the attributes the
``_hours_status`` -> ``is_open_now`` -> ``effective_hours_structured``
chain reads) to avoid pulling in the full ``Provider`` ORM model + a
session. ``hours_structured`` uses the full weekday keys (``monday``,
``tuesday``, etc.) -- matching ``_WEEKDAY_KEYS`` in
``app.providers.queries`` -- because that's the on-disk shape.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.home.queries import _CLOSING_SOON_MINUTES, _hours_status


class _StubProvider:
    """Minimal stand-in for ``Provider`` that satisfies the read chain."""

    def __init__(self, hours_structured: dict | None) -> None:
        self.hours_structured = hours_structured
        # ``effective_hours_structured`` checks ``provider.entity`` first.
        # Setting it to None (via missing attribute) makes getattr return
        # None and the function falls through to hours_structured.

    def __getattr__(self, name: str):
        # Any attribute the chain reaches for (e.g. .entity) that wasn't set
        # comes back as None. This keeps the stub small without listing every
        # touchpoint -- which would couple this test to internal field churn.
        return None


# 2026-05-25 is a Monday. Use these fixed datetimes throughout for
# reproducibility (no clock-time, no tz coupling).
MON_BEFORE_OPEN = datetime(2026, 5, 25, 7, 0)
MON_3H_BEFORE_CLOSE = datetime(2026, 5, 25, 14, 0)
MON_EXACTLY_30_MIN_LEFT = datetime(2026, 5, 25, 16, 30)
MON_15_MIN_LEFT = datetime(2026, 5, 25, 16, 45)
MON_31_MIN_LEFT = datetime(2026, 5, 25, 16, 29)
MON_AT_CLOSE = datetime(2026, 5, 25, 17, 0)
MON_AFTER_CLOSE = datetime(2026, 5, 25, 19, 0)
SAT_AFTERNOON = datetime(2026, 5, 30, 14, 0)


# Standard weekly hours: Mon-Fri 8 AM - 5 PM, weekends closed.
WEEKDAY_8_TO_5: dict = {
    "monday": [{"open": "08:00", "close": "17:00"}],
    "tuesday": [{"open": "08:00", "close": "17:00"}],
    "wednesday": [{"open": "08:00", "close": "17:00"}],
    "thursday": [{"open": "08:00", "close": "17:00"}],
    "friday": [{"open": "08:00", "close": "17:00"}],
    "saturday": [],
    "sunday": [],
}


def test_open_during_hours_returns_open_class() -> None:
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, text = _hours_status(p, now=MON_3H_BEFORE_CLOSE)
    assert state == "open"
    assert "Open" in text


def test_closing_soon_at_boundary_inclusive() -> None:
    """Exactly 30 minutes left counts as closing-soon (boundary <=, not <)."""
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, _ = _hours_status(p, now=MON_EXACTLY_30_MIN_LEFT)
    assert state == "closing-soon"


def test_closing_soon_well_inside_window() -> None:
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, _ = _hours_status(p, now=MON_15_MIN_LEFT)
    assert state == "closing-soon"


def test_open_just_outside_closing_soon_window() -> None:
    """31 minutes left should still be the open state, not closing-soon."""
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, _ = _hours_status(p, now=MON_31_MIN_LEFT)
    assert state == "open"


def test_closed_at_close_time() -> None:
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, _ = _hours_status(p, now=MON_AT_CLOSE)
    assert state == "closed"


def test_closed_after_close_time() -> None:
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, text = _hours_status(p, now=MON_AFTER_CLOSE)
    assert state == "closed"
    assert "Closed" in text


def test_closed_before_open_time_surfaces_opens_at() -> None:
    """Before-open state should tell the user when the place opens."""
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, text = _hours_status(p, now=MON_BEFORE_OPEN)
    assert state == "closed"
    assert "Opens" in text


def test_closed_on_a_weekday_with_empty_spans() -> None:
    """Empty list for the weekday means 'closed today', not unknown."""
    p = _StubProvider(WEEKDAY_8_TO_5)
    state, text = _hours_status(p, now=SAT_AFTERNOON)
    assert state == "closed"
    # When the spans list is empty, upstream returns "Closed today" copy.
    assert "Closed" in text


# ---------------------------------------------------------------------------
# Unknown state -- the C9 acceptance: no pill when we have no data
# ---------------------------------------------------------------------------


def test_unknown_when_hours_structured_is_none() -> None:
    p = _StubProvider(None)
    state, text = _hours_status(p, now=MON_3H_BEFORE_CLOSE)
    assert state == "unknown"
    assert text == "Hours on profile"


def test_unknown_when_hours_structured_is_empty_dict() -> None:
    p = _StubProvider({})
    state, text = _hours_status(p, now=MON_3H_BEFORE_CLOSE)
    assert state == "unknown"
    assert text == "Hours on profile"


def test_unknown_when_weekday_key_missing() -> None:
    """If hours dict has some days but not today's, treat as unknown."""
    p = _StubProvider({"saturday": [{"open": "10:00", "close": "16:00"}]})
    state, text = _hours_status(p, now=MON_3H_BEFORE_CLOSE)
    assert state == "unknown"
    assert text == "Hours on profile"


# ---------------------------------------------------------------------------
# Closing-soon window constant -- guard against accidental tuning
# ---------------------------------------------------------------------------


def test_closing_soon_window_is_30_minutes() -> None:
    """The 30-minute closing-soon window is the spec value (B5.2).
    Changing it requires explicit spec revision.
    """
    assert _CLOSING_SOON_MINUTES == 30


# ---------------------------------------------------------------------------
# State machine completeness -- only the four allowed classes ever return
# ---------------------------------------------------------------------------


ALLOWED_STATES = frozenset({"open", "closing-soon", "closed", "unknown"})


@pytest.mark.parametrize(
    "hours,now",
    [
        (WEEKDAY_8_TO_5, MON_3H_BEFORE_CLOSE),
        (WEEKDAY_8_TO_5, MON_EXACTLY_30_MIN_LEFT),
        (WEEKDAY_8_TO_5, MON_AT_CLOSE),
        (WEEKDAY_8_TO_5, MON_AFTER_CLOSE),
        (WEEKDAY_8_TO_5, SAT_AFTERNOON),
        (None, MON_3H_BEFORE_CLOSE),
        ({}, MON_3H_BEFORE_CLOSE),
    ],
)
def test_only_allowed_state_classes_returned(hours, now) -> None:
    p = _StubProvider(hours)
    state, _ = _hours_status(p, now=now)
    assert state in ALLOWED_STATES, (
        f"_hours_status returned out-of-spec state {state!r}. Allowed: {sorted(ALLOWED_STATES)}"
    )
