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
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote

from app.chat.intent_classifier import IntentResult
from app.chat.tier2_schema import Tier2Filters
from app.core.timezone import now_lake_havasu
from app.home.queries import _format_phone
from app.providers.photo_urls import google_photo_url
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


def _is_spotlight_now(row: dict[str, Any], *, now: datetime) -> bool:
    """True when a provider row is a paid spotlight active at ``now``.

    Mirrors the filter in ``app/home/queries.py:spotlights``. The voice
    answer path MUST NOT call this — spotlight status is a rendering signal only.
    """
    if (row.get("tier") or "") != "spotlight":
        return False
    until = row.get("sponsored_until")
    if until is None:
        return True
    if hasattr(until, "tzinfo") and until.tzinfo is None and now.tzinfo is not None:
        return until > now.replace(tzinfo=None)
    return until > now


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
    any_spotlight = False
    for row in provider_rows[:5]:
        item = _provider_row_to_business_item(row, now=now)
        if item is None:
            continue
        if _is_spotlight_now(row, now=now):
            item["spotlight"] = True
            any_spotlight = True
        items.append(item)
    cat_label = _pretty_category_label(category)
    payload: dict[str, Any] = {
        "category": cat_label,
        "total_count": total_count,
        "items": items,
    }
    if any_spotlight:
        payload["disclosure"] = True
    return payload


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
    seen_events: set[tuple[Any, ...]] = set()
    for r in rows:
        if r.get("type") == "event":
            key = (
                r.get("name"),
                r.get("date"),
                r.get("start_time"),
                r.get("location_name"),
            )
            if key in seen_events:
                continue
            seen_events.add(key)
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


# ─────────── card_row builder ───────────


_CARD_ROW_INTENT_RE = re.compile(
    r"\b("
    r"date\s*night|"
    r"romantic|"
    r"good\s+(?:for|spot|spots|place|places)\s+(?:for|to)|"
    r"where(?:'s|\s+is|\s+are)?\s+(?:a\s+)?good|"
    r"best\s+(?:spot|spots|place|places)\s+(?:for|to)|"
    r"recommend\s+(?:me\s+)?(?:somewhere|some\s+places?|a\s+spot)|"
    r"any\s+(?:good\s+)?(?:spots?|places?|recs?)\s+(?:for|to)|"
    r"top\s+(?:spots?|places?|picks?)|"
    r"what(?:'s|\s+is|\s+are)\s+(?:a\s+)?good\s+(?:spot|place|pick)"
    r")\b",
    re.IGNORECASE,
)


def is_card_row_query(
    query: str,
    filters: Tier2Filters,
    rows: list[dict[str, Any]],
) -> bool:
    """True when the query asks for a curated short list of 2–3 venues/events.

    Conservative — mirrors is_day_agenda_query's discipline. Requires ALL of:
      * query matches a recommendation-shape regex (see _CARD_ROW_INTENT_RE),
      * filters do NOT narrow to a single day (day_agenda owns that),
      * filters do NOT scope a 7-day window (week_strip owns that),
      * 2 <= len(rows) <= 6 (we display up to 3 cards; 1 reads as a sentence,
        7+ is a listing → business_list owns it),
      * NOT mostly-providers when filters.category is set (those are
        business listings — tier2_business_shortcut owns that path).

    Day_agenda and week_strip both run BEFORE this in tier2_handler — this
    detector is the last gate before the long-prose formatter.
    """
    if not rows:
        return False
    if not _CARD_ROW_INTENT_RE.search(query or ""):
        return False
    if _filters_narrow_to_single_day(filters):
        return False
    if _filters_scope_week_window(filters):
        return False
    if len(rows) < 2 or len(rows) > 6:
        return False
    if filters.category:
        provider_rows = [r for r in rows if r.get("type") == "provider"]
        if provider_rows and len(provider_rows) / len(rows) >= 0.66:
            return False
    return True


def build_card_row(
    filters: Tier2Filters, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the ``data`` dict for a ``card_row`` component.

    Schema (matches app/static/js/chat-new.js:392 renderer):

      {
        "items": [
          { "title":      str,
            "blurb":      str | None,
            "meta":       str | None,
            "image_url":  str | None,
            "image_alt":  str | None,
            "url":        str,
            "category":   str,
            "category_warm": bool },
          # exactly 2–3 items, max 3
        ]
      }
    """
    del filters  # reserved for future filter-aware ranking
    if not rows:
        return {"items": []}

    ranked = sorted(
        rows,
        key=lambda r: (
            0 if (r.get("type") == "provider" and r.get("thumb_url")) else 1,
            str(r.get("name") or ""),
        ),
    )
    items = [_row_to_card_item(r) for r in ranked[:3]]
    return {"items": items}


def _row_to_card_item(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a tier2 row dict to a card_row mini-card item."""
    if row.get("type") == "event":
        tags = [t for t in (row.get("tags") or []) if isinstance(t, str)]
        category = _pretty_category_from_tags(tags) or "Event"
        date_label = _event_card_date_label(row)
        start_time = (row.get("start_time") or "").strip()
        meta_parts = [p for p in (date_label, start_time) if p]
        meta = " · ".join(meta_parts) if meta_parts else None
        desc = str(row.get("description") or "").strip()
        return {
            "title": row.get("name") or "",
            "blurb": _truncate_blurb(desc) if desc else None,
            "meta": meta,
            "image_url": None,
            "image_alt": None,
            "url": _event_url(row),
            "category": category,
            "category_warm": _is_warm_category(category, tags),
        }

    name = str(row.get("name") or "").strip()
    slug = str(row.get("slug") or "").strip()
    address = str(row.get("address") or "").strip()
    desc = str(row.get("description") or "").strip()
    thumb = row.get("thumb_url")
    return {
        "title": name,
        "blurb": _truncate_blurb(desc) if desc else None,
        "meta": _short_address(address) or None,
        "image_url": thumb if thumb else None,
        "image_alt": name or None,
        "url": f"/provider/{slug}" if slug else "",
        "category": _trade_category_label(row) or "Place",
        "category_warm": False,
    }


def _event_card_date_label(row: dict[str, Any]) -> str | None:
    raw = row.get("date")
    if not raw:
        return None
    try:
        d = date.fromisoformat(str(raw)[:10])
        return d.strftime("%a %b ") + str(d.day)
    except (ValueError, TypeError):
        return None


def _truncate_blurb(text: str, limit: int = 120) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def fallback_card_row_voice(rows: list[dict[str, Any]], query: str) -> str:
    """Deterministic short voice line for the card row."""
    del query
    n = len(rows)
    if n == 2:
        return "Two solid bets for that. Quick picks below."
    if n == 3:
        return "Three to pick from — quick picks below."
    return "Few decent options. Top three below."


# ─────────── single_card + single_business_card builders ───────────

_TIER1_FACTUAL_SUBINTENTS = frozenset({
    "REVIEW_COUNT_LOOKUP",
    "RATING_LOOKUP",
    "WEBSITE_LOOKUP",
    "PHONE_LOOKUP",
    "AGE_LOOKUP",
    "COST_LOOKUP",
    "TIME_LOOKUP",
    "HOURS_LOOKUP",
    "LOCATION_LOOKUP",
    "DATE_LOOKUP",
    "OPEN_NOW",
    "URGENT_NOW",
    "LIST_BY_CATEGORY",
})

_SINGLE_ENTITY_ABOUT_SUBINTENTS = frozenset({
    None,
    "OPEN_ENDED",
    "NEXT_OCCURRENCE",
})


def _normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip())


def _row_matches_entity(entity: str, row: dict[str, Any]) -> bool:
    name = str(row.get("name") or "").strip()
    if not name or not entity.strip():
        return False
    en = _normalize_entity_name(entity)
    rn = _normalize_entity_name(name)
    return en == rn or en in rn or rn in en


def _is_about_sub_intent(sub_intent: str | None) -> bool:
    if sub_intent in _TIER1_FACTUAL_SUBINTENTS:
        return False
    return sub_intent in _SINGLE_ENTITY_ABOUT_SUBINTENTS


def _matching_rows_for_entity(
    entity: str, rows: list[dict[str, Any]], *, row_types: tuple[str, ...]
) -> list[dict[str, Any]]:
    return [
        r for r in rows
        if r.get("type") in row_types and _row_matches_entity(entity, r)
    ]


def pick_single_entity_row(
    entity: str, rows: list[dict[str, Any]], *, row_types: tuple[str, ...]
) -> dict[str, Any] | None:
    """Return the sole matching row when exactly one entity row is present."""
    matches = _matching_rows_for_entity(entity, rows, row_types=row_types)
    return matches[0] if len(matches) == 1 else None


def is_single_card_query(
    intent_result: IntentResult, rows: list[dict[str, Any]]
) -> bool:
    """True when the query names a single event/venue and asks 'what is it'."""
    entity = (intent_result.entity or "").strip()
    if not entity:
        return False
    if not _is_about_sub_intent(intent_result.sub_intent):
        return False
    matches = _matching_rows_for_entity(entity, rows, row_types=("event",))
    return len(matches) == 1


def is_single_business_card_query(
    intent_result: IntentResult, rows: list[dict[str, Any]]
) -> bool:
    """True when the query names a single service provider for 'about'."""
    entity = (intent_result.entity or "").strip()
    if not entity:
        return False
    if not _is_about_sub_intent(intent_result.sub_intent):
        return False
    matches = _matching_rows_for_entity(entity, rows, row_types=("provider",))
    if len(matches) != 1:
        return False
    row = matches[0]
    if row.get("google_place_id"):
        return True
    cat = str(row.get("category") or row.get("google_primary_category") or "").strip()
    return bool(cat)


def _format_time_display(hhmm: str) -> str:
    raw = hhmm.strip()
    if not raw:
        return ""
    try:
        hour_str, minute_str = raw.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
    except (ValueError, AttributeError):
        return raw
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    if minute:
        return f"{display_hour}:{minute:02d} {suffix}"
    return f"{display_hour} {suffix}"


def _format_event_when(row: dict[str, Any]) -> str | None:
    date_label = _event_card_date_label(row)
    start = (row.get("start_time") or "").strip()
    start_label = _format_time_display(start) if start else ""
    parts = [p for p in (date_label, start_label) if p]
    return ", ".join(parts) if parts else None


def _truncate_summary(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _provider_image_url(row: dict[str, Any]) -> str | None:
    thumb = row.get("thumb_url")
    if isinstance(thumb, str) and thumb.strip():
        return thumb.strip()
    refs = row.get("google_photo_refs")
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, str) and ref.strip():
                url = google_photo_url(ref.strip())
                if url:
                    return url
    return None


def _format_hours_block(row: dict[str, Any]) -> str | None:
    hours = str(row.get("hours") or "").strip()
    if hours:
        return hours
    structured = row.get("hours_structured")
    if not isinstance(structured, dict) or not structured:
        return None
    lines: list[str] = []
    for day, spans in structured.items():
        if not isinstance(spans, list) or not spans:
            continue
        parts: list[str] = []
        for span in spans:
            if not isinstance(span, dict):
                continue
            open_t = str(span.get("open") or "").strip()
            close_t = str(span.get("close") or "").strip()
            if open_t and close_t:
                parts.append(f"{open_t}–{close_t}")
        if parts:
            lines.append(f"{str(day).title()}: {', '.join(parts)}")
    return "\n".join(lines) if lines else None


def _format_rating_fact(row: dict[str, Any]) -> str | None:
    rating = row.get("google_rating")
    count = row.get("google_review_count")
    if not isinstance(rating, (int, float)):
        return None
    label = f"{float(rating):.1f}"
    if isinstance(count, int) and count > 0:
        label += f" ({count} reviews)"
    return label


def _format_review_snippet(row: dict[str, Any]) -> str | None:
    snippets = row.get("google_review_snippets")
    if not isinstance(snippets, list) or not snippets:
        return None
    first = snippets[0]
    if not isinstance(first, dict):
        return None
    text = str(first.get("text") or "").strip()
    attr = str(first.get("attribution") or "").strip()
    if not text:
        return None
    if len(text) > 140:
        text = text[:137].rstrip() + "…"
    quoted = f"'{text}'"
    return f"{quoted} — {attr}" if attr else quoted


def build_single_card(
    intent_result: IntentResult, row: dict[str, Any]
) -> dict[str, Any]:
    """Build the ``data`` dict for a ``single_card`` component."""
    del intent_result
    tags = [t for t in (row.get("tags") or []) if isinstance(t, str)]
    category = _pretty_category_from_tags(tags) or "Event"
    summary = _truncate_summary(str(row.get("description") or ""), 200)
    facts: list[dict[str, Any]] = []
    when = _format_event_when(row)
    if when:
        facts.append({"key": "When", "val": when})
    venue = str(row.get("location_name") or "").strip()
    if venue:
        fact: dict[str, Any] = {"key": "Where", "val": venue}
        maps_url = _maps_directions_url(venue)
        if maps_url:
            fact["val_url"] = maps_url
        facts.append(fact)
    cost = str(row.get("cost") or "").strip()
    if cost:
        facts.append({"key": "Cost", "val": cost})
    ages = str(row.get("age_range") or "").strip()
    if ages:
        facts.append({"key": "Ages", "val": ages})
    contact = str(row.get("contact_phone") or row.get("phone") or "").strip()
    if contact:
        facts.append({"key": "Contact", "val": contact})
    actions: list[dict[str, Any]] = []
    event_url = _event_url(row)
    if event_url:
        actions.append({"label": "Register", "url": event_url, "primary": True})
    if venue:
        directions = _maps_directions_url(venue)
        if directions:
            actions.append({"label": "Directions", "url": directions})
    return {
        "title": row.get("name") or "",
        "image_url": None,
        "image_alt": None,
        "summary": summary,
        "category": category,
        "category_warm": _is_warm_category(category, tags),
        "facts": facts,
        "actions": actions,
    }


def build_single_business_card(
    intent_result: IntentResult, row: dict[str, Any]
) -> dict[str, Any]:
    """Build the ``data`` dict for a ``single_business_card`` component."""
    del intent_result
    now = now_lake_havasu()
    status_class, status_text = _open_status_for_row(row, now=now)
    summary = _truncate_summary(
        str(row.get("featured_description") or row.get("description") or ""), 200
    )
    address = str(row.get("address") or "").strip()
    address_short = _short_address(address)
    directions_url = _maps_directions_url(address) if address else None
    phone_display, phone_raw = _format_phone(row.get("phone"))
    website = str(row.get("website") or "").strip()
    facts: list[dict[str, Any]] = []
    hours_block = _format_hours_block(row)
    if hours_block:
        facts.append({"key": "Hours", "val": hours_block})
    if address_short or address:
        fact: dict[str, Any] = {"key": "Address", "val": address_short or address}
        if directions_url:
            fact["val_url"] = directions_url
        facts.append(fact)
    rating = _format_rating_fact(row)
    if rating:
        facts.append({"key": "Rating", "val": rating})
    review = _format_review_snippet(row)
    if review:
        facts.append({"key": "Recent review", "val": review})
    actions: list[dict[str, Any]] = []
    if phone_raw:
        actions.append({"label": "Call", "url": f"tel:{phone_raw}", "primary": True})
    if website:
        actions.append({"label": "Website", "url": website})
    if directions_url:
        actions.append({"label": "Directions", "url": directions_url})
    payload: dict[str, Any] = {
        "title": row.get("name") or "",
        "image_url": _provider_image_url(row),
        "image_alt": row.get("name") or None,
        "summary": summary,
        "category": _trade_category_label(row) or "Business",
        "category_warm": False,
        "status": status_class,
        "status_class": status_class,
        "status_text": status_text,
        "facts": facts,
        "actions": actions,
    }
    if _is_spotlight_now(row, now=now):
        payload["spotlight"] = True
    return payload


def fallback_single_card_voice(row: dict[str, Any], *, is_business: bool) -> str:
    """Deterministic short voice line. Used when the LLM is unavailable."""
    name = str(row.get("name") or "That one").strip()
    if is_business:
        category = _trade_category_label(row) or "local spot"
        now = now_lake_havasu()
        status_class, status_text = _open_status_for_row(row, now=now)
        if status_class == "open" and status_text:
            tail = status_text.split("·")[-1].strip() if "·" in status_text else status_text
            return f"{name} — {category}. {tail}."
        rating = _format_rating_fact(row)
        if rating:
            return f"{name} — {category}. {rating} on Google."
        return f"{name} — {category}. Solid local pick."
    when = _format_event_when(row) or "soon"
    summary = str(row.get("description") or "").strip()
    if summary:
        sentence = _truncate_summary(summary, 120).rstrip(".")
        return f"{name} on {when}. {sentence}."
    return f"{name} on {when}. Worth a look."
