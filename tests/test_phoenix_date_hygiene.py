"""P1-8: Lake Havasu (America/Phoenix) date hygiene.

``date.today()`` on a UTC host rolls a day early after ~5 PM local, so date
math that should be anchored to the user's wall clock must use
``now_lake_havasu().date()`` instead.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.core import ranking, slots

_LHC = ZoneInfo("America/Phoenix")

# 10 PM Phoenix on 2026-06-06 — UTC has already rolled to 2026-06-07, the exact
# window where date.today() (UTC) and the local date disagree.
_FIXED_LHC_EVENING = datetime(2026, 6, 6, 22, 0, tzinfo=_LHC)


def test_extract_date_range_today_uses_lake_havasu_date() -> None:
    with patch("app.core.slots.now_lake_havasu", return_value=_FIXED_LHC_EVENING):
        dr = slots.extract_date_range("what's on today")
    assert dr == {"start": date(2026, 6, 6), "end": date(2026, 6, 6)}


def test_compute_event_card_rank_defaults_today_to_lake_havasu() -> None:
    """With today unset, the function must default to the Lake Havasu date —
    i.e. behave identically to passing that date explicitly."""
    event = object()
    with patch("app.core.ranking.now_lake_havasu", return_value=_FIXED_LHC_EVENING):
        defaulted = ranking.compute_event_card_rank(event=event, occurrence_date=date(2026, 6, 6))
    explicit = ranking.compute_event_card_rank(
        event=event, occurrence_date=date(2026, 6, 6), today=date(2026, 6, 6)
    )
    assert defaulted == explicit
    # Sanity: same-day occurrence gets the day-0 boost (1.30), proving the date
    # resolved to 2026-06-06 rather than the UTC-rolled 2026-06-07.
    assert defaulted == 1.30
