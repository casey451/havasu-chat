"""Builders that turn Tier 2 ``rows`` into structured component payloads.

BUILD.md step 5 / task #12. The chat backend already has a beautiful pipeline
that classifies intent, extracts filters, queries the catalog, and runs an
LLM formatter for prose. This module adds a sibling layer that — for queries
of a shape the front-end can render structurally — bypasses the long-prose
formatter and emits a deterministic ``component`` payload (plus a short
voice line) instead.

Today this implements only the **day_agenda** shape ("what's happening
Friday?"). week_strip / card_row / business_list builders land in their
own steps. Each builder is pure: input is filters + rows, output is a
``data`` dict shaped for the front-end renderer in ``chat-new.js``. No
LLM, no DB, no side effects.

Detection logic (``is_day_agenda_query``) is intentionally conservative —
when in doubt, return False so the existing formatter path runs and the
front-end falls back to voice-only rendering. Better to miss a chance at
a pretty component than to wrongly classify a single-venue lookup or a
category-browse query.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.chat.tier2_schema import Tier2Filters
from app.core.timezone import now_lake_havasu

# ─────────── shape detection ───────────


def is_day_agenda_query(filters: Tier2Filters, rows: list[dict[str, Any]]) -> bool:
    """True when the query narrows to a single day with a list of events.

    Conservative: requires both a single-day date-shape AND a mostly-event
    result set with at least 2 rows. Single-event days fall through to
    the existing formatter (one event reads naturally as a sentence; the
    component shape is overkill).
    """
    if not rows:
        return False
    if len(rows) < 2:
        # One row reads better as a sentence than as a 1-row "agenda".
        return False

    event_rows = [r for r in rows if r.get("type") == "event"]
    if len(event_rows) < 2:
        return False
    # Mostly events. If the result set is half providers, it's a category
    # browse, not a day agenda.
    if len(event_rows) / len(rows) < 0.66:
        return False

    return _filters_narrow_to_single_day(filters)


def _filters_narrow_to_single_day(f: Tier2Filters) -> bool:
    """The filter set scopes to exactly one calendar day."""
    if f.date_exact is not None:
        return True

    # date_start == date_end (or date_end omitted) → single-day window
    if f.date_start is not None and (f.date_end is None or f.date_end == f.date_start):
        return True

    if f.time_window in ("today", "tomorrow"):
        return True

    if f.day_of_week and len(f.day_of_week) == 1:
        return True

    return False


def resolve_target_date(f: Tier2Filters) -> date:
    """The calendar date the query is asking about. Best-effort.

    Falls back to today when the filters are vague (used by the voice
    template; shouldn't happen for day-shape queries that pass detection).
    """
    if f.date_exact is not None:
        return f.date_exact
    if f.date_start is not None:
        return f.date_start

    today = now_lake_havasu().date()
    if f.time_window == "today":
        return today
    if f.time_window == "tomorrow":
        return today + timedelta(days=1)

    if f.day_of_week and len(f.day_of_week) == 1:
        target = _DOW_INDEX.get(f.day_of_week[0].lower())
        if target is not None:
            # Next occurrence of that weekday (today counts).
            delta = (target - today.weekday()) % 7
            return today + timedelta(days=delta)
    return today


_DOW_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


# ─────────── day_agenda builder ───────────


def build_day_agenda(
    filters: Tier2Filters, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the ``data`` dict for a ``day_agenda`` component.

    Mirrors the schema in BUILD.md "Answer rendering contract":

      { date, date_label, events: [{title, start, end, venue, category, ... }] }

    Sorted by start_time. Non-event rows in the result set (rare for a
    day-shape query, but possible) are included with no time and a more
    generic category — better to surface them than drop them.
    """
    target = resolve_target_date(filters)
    events_in: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for r in rows:
        if r.get("type") == "event":
            events_in.append(r)
        else:
            other.append(r)

    # Stable sort by (start_time, name) so the JS renderer's
    # morning/afternoon/evening grouping reads cleanly.
    events_in.sort(key=lambda r: (r.get("start_time") or "99:99", r.get("name") or ""))

    out_events: list[dict[str, Any]] = []
    for r in events_in:
        out_events.append(_event_to_agenda_item(r))
    for r in other:
        out_events.append(_other_to_agenda_item(r))

    return {
        "date": target.isoformat(),
        "date_label": target.strftime("%A, %B ") + str(target.day),
        "events": out_events,
    }


def _event_to_agenda_item(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a tier2 event-row dict to an agenda_row item.

    Categories: pull a single readable category from tags. Festivals and
    food lean warm; otherwise teal. The front-end uses ``category_warm``
    to switch the dot color.
    """
    tags = [t for t in (row.get("tags") or []) if isinstance(t, str)]
    category = _pretty_category_from_tags(tags) or "Event"
    item: dict[str, Any] = {
        "title": row.get("name") or "",
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "venue": row.get("location_name") or "",
        "category": category,
        "category_warm": _is_warm_category(category, tags),
        "url": _event_url(row),
    }
    # Date range is shown as a "May 8 – 10" label when present.
    if row.get("end_date") and row.get("end_date") != row.get("date"):
        try:
            start_d = date.fromisoformat(row["date"])
            end_d = date.fromisoformat(row["end_date"])
            item["range_label"] = (
                f"{start_d.strftime('%b ')}{start_d.day} – {end_d.day}"
            )
        except (ValueError, TypeError):
            pass
    return item


def _other_to_agenda_item(row: dict[str, Any]) -> dict[str, Any]:
    """Best-effort agenda row for non-event types."""
    return {
        "title": row.get("name") or "",
        "venue": row.get("location") or row.get("address") or "",
        "category": (row.get("activity_category") or row.get("category") or "Other").title(),
        "category_warm": False,
        "url": "",
    }


_WARM_KEYWORDS = ("festival", "food", "music", "live", "concert", "wine", "beer", "restaurant", "bar")


def _is_warm_category(category: str, tags: list[str]) -> bool:
    needle = " ".join([category.lower(), *(t.lower() for t in tags)])
    return any(k in needle for k in _WARM_KEYWORDS)


def _pretty_category_from_tags(tags: list[str]) -> str | None:
    """Pick the most readable category-ish tag from a tag list.

    Tag content is messy in the catalog. Prefer a known content category
    (BUILD.md mentions arts/sports/aquatics/food/fitness/recreation) when
    available. Otherwise return the first capitalized tag, or None.
    """
    if not tags:
        return None
    known = {"arts", "sports", "aquatic", "aquatics", "food", "fitness", "recreation",
             "music", "festival", "kids", "family", "drinks"}
    lower_tags = [(t, t.lower()) for t in tags if isinstance(t, str)]
    for original, lower in lower_tags:
        if lower in known:
            return original.title() if original.islower() else original
    # Fallback: first short tag
    for original, lower in lower_tags:
        if 2 <= len(original) <= 24:
            return original.title() if original.islower() else original
    return None


def _event_url(row: dict[str, Any]) -> str:
    """Prefer registration/event URL; fall back to the event detail page."""
    url = (row.get("event_url") or "").strip()
    if url:
        return url
    # No id field on the row dict — the formatter accepts the row dict
    # without id and we can't synthesize /events/<id> here. Empty string
    # is honored by the renderer (just no link).
    return ""


# ─────────── short voice line for day_agenda ───────────


def fallback_day_agenda_voice(rows: list[dict[str, Any]], target: date) -> str:
    """Deterministic short voice line. Used when the LLM is unavailable.

    Pattern: "<Day>'s <busy/quiet> — N things, <where most are>."

    Hand-tuned to match Hava's voice: declarative, no question marks,
    1 sentence, period at the end. Mirrors the example in BUILD.md
    ("Friday's busy — eight things, mostly at the Aquatic Center, plus
    the Pro Watercross weekend kicks off at noon.").
    """
    n = len(rows)
    if n == 0:
        return f"{target.strftime('%A')}'s quiet — nothing on the calendar."

    descriptor = _busy_descriptor(n)
    word = _spell_count(n)
    location_clause = _top_location_clause(rows)

    if location_clause:
        return f"{target.strftime('%A')}'s {descriptor} — {word} things, {location_clause}."
    return f"{target.strftime('%A')}'s {descriptor} — {word} things on the calendar."


def _busy_descriptor(n: int) -> str:
    if n >= 6:
        return "busy"
    if n >= 3:
        return "got a few"
    return "light"


def _spell_count(n: int) -> str:
    return {
        1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
        6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    }.get(n, str(n))


def _top_location_clause(rows: list[dict[str, Any]]) -> str | None:
    """If most rows share a venue, name it. Otherwise return None."""
    venues: dict[str, int] = {}
    for r in rows:
        venue = (r.get("location_name") or "").strip()
        if venue:
            venues[venue] = venues.get(venue, 0) + 1
    if not venues:
        return None
    top, count = max(venues.items(), key=lambda kv: kv[1])
    if count >= 2 and count >= len(rows) / 2:
        return f"mostly at the {top}" if not top.lower().startswith("the ") else f"mostly at {top}"
    return None
