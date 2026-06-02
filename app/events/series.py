"""Collapse recurring event series at render time (P0 Task 4).

The events feed is flooded because a weekly class like *Lap Swim* is stored as
one physical ``Event`` row per occurrence (28 rows, all ``is_recurring=0`` /
``rrule=NULL``) rather than one row with a recurrence rule. This module detects
those series by their natural key — ``(normalized_title, location, start_time)``
— infers the weekday pattern over a look-ahead horizon, and collapses each series
to a single feed entry ("Lap Swim · Mon–Fri · 5:00 AM") anchored on its next
occurrence, with a "runs regularly" flag.

Pure / DB-free: callers pass the rows they already fetched. ``build_series_index``
consumes a horizon of ``(title, location, start_time, date)`` tuples; the feed
builder then asks the index whether a given row is part of a recurring series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

_WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# A series is "recurring" once it has at least this many occurrences across the
# look-ahead horizon. Two occurrences could be a coincidence (e.g. a two-night
# festival); three+ on a weekly cadence is a class/ongoing series.
RECURRING_MIN_OCCURRENCES = 3


def series_key(
    normalized_title: str | None, location_normalized: str | None, start_time: time | None
) -> tuple[str, str, str]:
    """Natural key identifying a recurring series across its occurrence rows."""
    return (
        (normalized_title or "").strip().lower(),
        (location_normalized or "").strip().lower(),
        start_time.strftime("%H:%M") if start_time else "",
    )


@dataclass
class SeriesInfo:
    weekdays: set[int] = field(default_factory=set)  # 0=Mon .. 6=Sun
    dates: list[date] = field(default_factory=list)
    is_recurring_flag: bool = False

    @property
    def count(self) -> int:
        return len(self.dates)

    @property
    def is_series(self) -> bool:
        return self.count >= RECURRING_MIN_OCCURRENCES or self.is_recurring_flag


def build_series_index(
    rows: list[tuple[str | None, str | None, time | None, date, bool]],
) -> dict[tuple[str, str, str], SeriesInfo]:
    """Aggregate horizon rows into per-series weekday patterns.

    Each row is ``(normalized_title, location_normalized, start_time, date,
    is_recurring)``. Returns ``series_key -> SeriesInfo``.
    """
    index: dict[tuple[str, str, str], SeriesInfo] = {}
    for title, loc, start_time, occ_date, is_recurring in rows:
        key = series_key(title, loc, start_time)
        info = index.setdefault(key, SeriesInfo())
        info.dates.append(occ_date)
        info.weekdays.add(occ_date.weekday())
        if is_recurring:
            info.is_recurring_flag = True
    return index


def schedule_label(weekdays: set[int]) -> str:
    """Human schedule from a weekday set: 'Daily', 'Mon–Fri', 'Weekends',
    a contiguous range ('Tue–Thu'), or an explicit list ('Mon, Wed, Fri')."""
    if not weekdays:
        return ""
    wd = sorted(weekdays)
    wd_set = set(wd)
    if wd_set == set(range(7)):
        return "Daily"
    if wd_set == {0, 1, 2, 3, 4}:
        return "Mon–Fri"
    if wd_set == {5, 6}:
        return "Weekends"
    # Contiguous run of 3+ days -> abbreviated range.
    if len(wd) >= 3 and wd == list(range(wd[0], wd[-1] + 1)):
        return f"{_WEEKDAY_ABBR[wd[0]]}–{_WEEKDAY_ABBR[wd[-1]]}"
    return ", ".join(_WEEKDAY_ABBR[d] for d in wd)
