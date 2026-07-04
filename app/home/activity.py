"""Date-strip activity indicator (v4.4 PR-7, DATA_CONTRACTS §2.3 / DESIGN_SPEC §6.4).

Dots signal how busy a day is; a configured headliner date shows a brass spark
instead. Config only — no DB, no migration (BUILD_PLAN decision 8).

Perf note (decision 15, see PROGRESS.md): the dots derive from the date strip's
already-computed per-day total (one-offs + classes), NOT ``day_counts`` — a single
``day_counts`` build measured ~560 ms, so 7 of them would add ~4 s to every home
render. The strip total is the honest "how busy" number the card already shows.
"""

from __future__ import annotations

from datetime import date

# Headliner dates → the spark's tooltip text. Seed only; extend as events warrant.
HEADLINER_DATES: dict[str, str] = {
    "2026-07-04": "4th of July Fireworks at the Beach · 9 PM",
}


def activity_dots(total: int) -> int:
    """Dot count for a day's activity: 1–19 → 1, 20–49 → 2, ≥50 → 3, 0 → none."""
    if total <= 0:
        return 0
    if total <= 19:
        return 1
    if total <= 49:
        return 2
    return 3


def strip_activity(total: int, d: date) -> dict[str, object]:
    """The activity marker for one date-strip card.

    A headliner date returns ``spark=True`` with its tooltip ``title`` (the spark
    replaces dots). Otherwise ``dots`` carries the threshold count.
    """
    headliner = HEADLINER_DATES.get(d.isoformat())
    if headliner:
        return {"spark": True, "title": headliner, "dots": 0}
    return {"spark": False, "title": None, "dots": activity_dots(total)}
