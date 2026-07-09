"""Single day-count service (v4.4 PR-3, DATA_CONTRACTS §2).

ONE base for "how much is happening on day D": the same number the home feed
renders, so the home headline/pills, the calendar agenda header, and the
date-strip activity dots (PR-7) can never disagree again (the F6 split: home 54,
agenda 17, a calendar cell implying 87 — three counting bases).

The base is authoritative because it IS the home feed's total
(:func:`app.home.events_views.calendar_day_view_model` ``["total"]`` = the sum of
every section's count: events + class sessions + venue-hours rows + movie titles
+ civic, after the same dedupe/filters the day builder applies). F6 already
pinned the home headline to it; this service is the single call site the other
summary surfaces now share.

NOTE (decision-15 judgment call, see PROGRESS.md): the glanceable month-cell
``+N more`` is deliberately NOT ``total - chips``. On class-heavy days the base is
~100 (70+ recurring class sessions), so ``total - chips`` would render "+90 more"
in every cell — reversing the 2026-07-01 month audit that moved recurring classes
into a separate "N classes" badge precisely to stop that flood, and breaking the
"glanceable calendar" guardrail. The cell keeps its two honest numbers (one-off
overflow + class badge); this service unifies the *summary headers* that users
actually compare (home "today" vs the selected-day agenda).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.home import events_views


@dataclass(frozen=True)
class DayCount:
    day: date
    total: int  # == the home feed's total for this day (the one base)
    by_group: dict[str, int]  # section key -> its count (for pills / breakdowns)


def day_counts(
    db: Session,
    d: date,
    *,
    now: datetime | None = None,
    family: bool = False,
    seniors: bool = False,
    vm: dict[str, Any] | None = None,
) -> DayCount:
    """The canonical count for day ``d``.

    Pass ``vm`` (a prebuilt ``calendar_day_view_model`` result) when the caller
    already has one, so the same day is never built twice in one render.
    """
    if vm is None:
        vm = events_views.calendar_day_view_model(
            db, day=d, now=now, family=family, seniors=seniors
        )
    by_group = {s["key"]: int(s.get("count") or 0) for s in vm.get("sections", [])}
    return DayCount(day=d, total=int(vm.get("total") or 0), by_group=by_group)
