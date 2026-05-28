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

import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

from app.chat.tier2_schema import Tier2Filters
from app.core.timezone import now_lake_havasu
from app.home.queries import _format_phone
from app.providers.queries import is_open_status_from_structured_hours

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


# ─────────── business_list builder (BUILD.md step 7.5) ───────────


def build_business_list(
    rows: list[dict[str, Any]],
    *,
    category: str,
    total_count: int,
    intent_query: str | None = None,
) -> dict[str, Any]:
    """Build the ``data`` dict for a ``business_list`` chat component.

    Maps tier-2 provider rows into the schema expected by ``renderBusinessList``
    in ``chat-new.js``. Items are capped at five, sorted by rating (highest
    first) to match the listing shortcut's prior prose ordering intent.
    """
    del intent_query  # reserved for future foot_link / query-aware copy
    provider_rows = [r for r in rows if r.get("type") == "provider"]
    provider_rows.sort(
        key=lambda r: (
            -(float(r["google_rating"]) if r.get("google_rating") is not None else -1.0),
            str(r.get("name") or ""),
        )
    )
    items: list[dict[str, Any]] = []
    now = now_lake_havasu()
    for row in provider_rows[:5]:
        item = _provider_row_to_business_item(row, now=now)
        if item is not None:
            items.append(item)
    cat_label = _pretty_category_label(category)
    return {
        "category": cat_label,
        "total_count": total_count,
        "items": items,
    }


def _pretty_category_label(category: str) -> str:
    from app.chat.tier2_business_shortcut import _pluralize_for_header

    plural = _pluralize_for_header(category or "businesses")
    return plural.title() if plural.islower() else plural


def _provider_row_to_business_item(
    row: dict[str, Any], *, now: Any
) -> dict[str, Any] | None:
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    slug = str(row.get("slug") or "").strip()
    url = f"/provider/{slug}" if slug else ""
    phone_display, phone_raw = _format_phone(row.get("phone"))
    address = str(row.get("address") or "").strip()
    address_short = _short_address(address)
    directions_url = _maps_directions_url(address) if address else None
    status_class, status_text = _open_status_for_row(row, now=now)
    rating = row.get("google_rating")
    review_count = row.get("google_review_count")
    item: dict[str, Any] = {
        "name": name,
        "url": url,
        "category": _trade_category_label(row),
        "address_short": address_short or address or None,
        "directions_url": directions_url,
    }
    if phone_display:
        item["phone"] = phone_display
    if phone_raw:
        item["phone_raw"] = phone_raw
    if isinstance(rating, (int, float)):
        item["rating"] = float(rating)
    if isinstance(review_count, int):
        item["review_count"] = review_count
    if row.get("thumb_url"):
        item["thumb_url"] = row["thumb_url"]
    desc = str(row.get("description") or "").strip()
    if desc:
        item["blurb"] = desc
    if status_class and status_class != "unknown":
        item["status"] = status_class
        item["status_class"] = status_class
        if status_text:
            item["status_text"] = status_text
    return item


def _short_address(address: str) -> str:
    """First line / street portion for compact card display."""
    line = address.split("\n", 1)[0].strip()
    if len(line) > 80:
        return line[:77] + "…"
    return line


def _maps_directions_url(address: str) -> str:
    query = address.strip()
    low = query.lower()
    if query and "lake havasu" not in low:
        query = f"{query}, Lake Havasu City AZ"
    elif query and " az" not in low and "arizona" not in low:
        query = f"{query} AZ"
    return "https://www.google.com/maps/search/?api=1&query=" + quote(query)


def _trade_category_label(row: dict[str, Any]) -> str:
    gpc = str(row.get("google_primary_category") or row.get("category") or "")
    gpc = re.sub(r"_+", " ", gpc).strip()
    if gpc:
        return gpc.title()
    return ""


def _open_status_for_row(row: dict[str, Any], *, now: Any) -> tuple[str, str]:
    """Map structured hours on a provider row to pill status for the renderer."""
    hours = row.get("hours_structured")
    is_open, status_copy = is_open_status_from_structured_hours(hours, now=now)
    if is_open is None:
        return "unknown", "Hours on profile"
    if is_open:
        return "open", status_copy or "Open now"
    return "closed", status_copy or "Closed now"


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


# ─────────── week_strip builder ───────────


def is_week_strip_query(filters: Tier2Filters, rows: list[dict[str, Any]]) -> bool:
    """True when the query asks about a 7-day window with multiple events.

    Conservative — mirrors is_day_agenda_query's discipline. Requires:
      * filters scope a multi-day window (this_week / next_week / a date_start
        with date_end >= date_start + 2 days),
      * AND >=4 event rows in the result set (a 7-day strip with only 1–2
        events reads worse than a sentence),
      * AND mostly-events (>= 0.66 ratio), same as day_agenda.
    """
    if not rows:
        return False
    if _filters_narrow_to_single_day(filters):
        return False
    if not _filters_scope_week_window(filters):
        return False

    event_rows = [r for r in rows if r.get("type") == "event"]
    if len(event_rows) < 4:
        return False
    if len(event_rows) / len(rows) < 0.66:
        return False
    return True


def _filters_scope_week_window(f: Tier2Filters) -> bool:
    """The filter set scopes to a multi-day week-shaped window."""
    if f.time_window in ("this_week", "next_week"):
        return True
    if f.date_start is not None and f.date_end is not None:
        return f.date_end >= f.date_start + timedelta(days=2)
    return False


def resolve_week_window(f: Tier2Filters) -> tuple[date, date]:
    """7-day calendar window for a week-shape query.

    * time_window == "this_week"  → today..today+6
    * time_window == "next_week"  → next Monday..next Sunday
    * date_start + date_end       → date_start..min(date_end, date_start+6)
    * fallback                    → today..today+6 (best-effort)
    """
    today = now_lake_havasu().date()
    if f.time_window == "this_week":
        start = today
        return start, start + timedelta(days=6)
    if f.time_window == "next_week":
        days_until = (7 - today.weekday()) % 7
        if days_until == 0:
            days_until = 7
        start = today + timedelta(days=days_until)
        return start, start + timedelta(days=6)
    if f.date_start is not None:
        start = f.date_start
        end = f.date_end if f.date_end is not None else start + timedelta(days=6)
        end = min(end, start + timedelta(days=6))
        return start, end
    start = today
    return start, start + timedelta(days=6)


def build_week_strip(
    filters: Tier2Filters, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the ``data`` dict for a ``week_strip`` component.

    Schema (matches app/static/js/chat-new.js:286 renderer):

      {
        "title": "May 28 – Jun 3",            # optional; JS computes if absent
        "total_count": int,                    # total event count across the 7 days
        "days": [
          { "date": "YYYY-MM-DD",
            "dow":  "Thu", "num": 28,         # convenience for the JS dot picker
            "count": int,                      # events on this day (dots, capped at 6)
            "is_today": bool },
          # ...exactly 7 entries
        ],
        "selected_date": "YYYY-MM-DD",         # default = first day with events,
                                               #          else window_start
        "agenda": [ <agenda_row items> ],     # same shape as day_agenda.events
                                               # for the selected_date only
      }
    """
    window_start, _window_end = resolve_week_window(filters)
    today = now_lake_havasu().date()

    buckets: dict[date, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("type") != "event":
            continue
        raw = r.get("date")
        if not raw:
            continue
        try:
            day = date.fromisoformat(str(raw)[:10])
        except (ValueError, TypeError):
            continue
        buckets.setdefault(day, []).append(r)

    days_out: list[dict[str, Any]] = []
    total_count = 0
    for i in range(7):
        d = window_start + timedelta(days=i)
        day_rows = buckets.get(d, [])
        count = len(day_rows)
        total_count += count
        days_out.append({
            "date": d.isoformat(),
            "dow": d.strftime("%a"),
            "num": d.day,
            "count": count,
            "is_today": d == today,
        })

    selected_date = window_start
    for cell in days_out:
        if cell["count"] > 0:
            selected_date = date.fromisoformat(cell["date"])
            break

    agenda_rows = buckets.get(selected_date, [])
    agenda_rows.sort(
        key=lambda r: (r.get("start_time") or "99:99", r.get("name") or "")
    )
    agenda = [_event_to_agenda_item(r) for r in agenda_rows]

    last_day = window_start + timedelta(days=6)
    title = (
        f"{window_start.strftime('%b ')}{window_start.day}"
        f" – {last_day.strftime('%b ')}{last_day.day}"
    )

    return {
        "title": title,
        "total_count": total_count,
        "days": days_out,
        "selected_date": selected_date.isoformat(),
        "agenda": agenda,
    }


def fallback_week_strip_voice(
    rows: list[dict[str, Any]], window: tuple[date, date]
) -> str:
    """Deterministic short voice line for the week. Used when LLM is unavailable.

    Pattern: "This week's <busy/quiet> — N things across <M> days, <where most are>."
    """
    event_rows = [r for r in rows if r.get("type") == "event"]
    n = len(event_rows)
    window_start, _ = window

    if n == 0:
        return "This week's quiet — nothing on the calendar."

    days_with_events: set[date] = set()
    for r in event_rows:
        raw = r.get("date")
        if not raw:
            continue
        try:
            days_with_events.add(date.fromisoformat(str(raw)[:10]))
        except (ValueError, TypeError):
            continue
    m = len(days_with_events)
    descriptor = _busy_descriptor(n)
    word = _spell_count(n)
    location_clause = _top_location_clause(event_rows)

    if m <= 1:
        day_phrase = "one day"
    else:
        day_phrase = f"{_spell_count(m)} days"

    if location_clause:
        return (
            f"This week's {descriptor} — {word} things across {day_phrase}, "
            f"{location_clause}."
        )
    return f"This week's {descriptor} — {word} things across {day_phrase}."
