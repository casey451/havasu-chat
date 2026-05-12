"""Deterministic Tier 2 rendering for all-event catalog rows (Session 2 follow-up).

Numbered lines use literal ``"1. "``, ``"2. "`` prefixes for chat display — not Markdown
list syntax. Layer 2 only parses ``[label](url)`` for click-through.
"""

from __future__ import annotations

import calendar
import html
from datetime import date
from typing import Any, Dict, List

# Visible blank line after header for pre-wrap chat bubbles (DESIGN 3).
_HEADER_BODY_SEPARATOR = "\n\n"


def _event_list_framing_line(query: str) -> str:
    """One landscape beat before multi-event lists (voice rubric §4.4 alignment)."""
    q = (query or "").lower()
    if any(k in q for k in ("kid", "kids", "family", "child", "children")):
        return "A few solid family-friendly picks on the calendar:"
    if any(k in q for k in ("weekend", "saturday", "sunday")):
        return "Weekend highlights around the lake:"
    if any(k in q for k in ("tonight", "today", "tomorrow")):
        return "Happening soon — worth a look:"
    if any(k in q for k in ("music", "concert", "band", "live")):
        return "Live music and shows on tap:"
    if "free" in q:
        return "Free or cheap happenings worth catching:"
    if any(k in q for k in ("sport", "game", "league")):
        return "Sports and league nights locals actually show up for:"
    return "A few solid options around town this window:"


def _parse_iso_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    return date.fromisoformat(str(s).strip()[:10])


def _format_calendar_date(d: date) -> str:
    """e.g. May 8, 2026 (no weekday)."""
    return f"{calendar.month_name[d.month]} {d.day}, {d.year}"


def _format_short_mdy(d: date) -> str:
    """e.g. Dec 31, 2025 for cross-year spans."""
    return f"{calendar.month_abbr[d.month]} {d.day}, {d.year}"


def _format_date_span(start: date, end: date) -> str:
    if start > end:
        start, end = end, start
    if start.year != end.year:
        return f"{_format_short_mdy(start)}–{_format_short_mdy(end)}"
    if start.month == end.month:
        return f"{calendar.month_name[start.month]} {start.day}–{end.day}, {start.year}"
    return f"{_format_calendar_date(start)}–{calendar.month_name[end.month]} {end.day}, {start.year}"


def _parse_hhmm(s: Any) -> tuple[int, int] | None:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    parts = t.split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return h, m


def _format_clock_12h(hour: int, minute: int) -> str:
    """12-hour with AM/PM; midnight -> 12:00 AM, noon -> 12:00 PM."""
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{minute:02d} {suffix}"


def _format_hhmm_12h(hm: Any) -> str | None:
    parsed = _parse_hhmm(hm)
    if parsed is None:
        return None
    return _format_clock_12h(parsed[0], parsed[1])


def _normalize_description_fragment(raw: str) -> str:
    d = raw.strip()
    if not d:
        return ""
    if d[-1] not in ".!?":
        return d + "."
    return d


def _event_url_nonempty(row: Dict[str, Any]) -> str | None:
    u = row.get("event_url")
    if u is None:
        return None
    s = str(u).strip()
    return s or None


def _location_nonempty(row: Dict[str, Any]) -> str | None:
    loc = row.get("location_name")
    if loc is None:
        return None
    s = str(loc).strip()
    return s or None


def _render_one_event_sentence(row: Dict[str, Any]) -> str:
    name = str(row.get("name", "") or "")
    if not name:
        raise ValueError("event row missing name")

    start_d = _parse_iso_date(row.get("date"))
    if start_d is None:
        raise ValueError("event row missing date")

    end_d = _parse_iso_date(row.get("end_date"))
    multi = end_d is not None and end_d != start_d

    st = _format_hhmm_12h(row.get("start_time"))
    et = _format_hhmm_12h(row.get("end_time"))

    loc = _location_nonempty(row)

    parts: list[str] = [name]

    if multi:
        span = _format_date_span(start_d, end_d)
        parts.append("runs")
        parts.append(span)
        if st and et:
            parts.append(f"from {st} to {et}")
        elif st:
            parts.append(f"at {st}")
        if loc:
            parts.append(f"at {loc}")
        core = " ".join(parts) + "."
    else:
        day = _format_calendar_date(start_d)
        parts.append("on")
        parts.append(day)
        if st and et:
            parts.append(f"from {st} to {et}")
        elif st:
            parts.append(f"at {st}")
        if loc:
            parts.append(f"at {loc}")
        core = " ".join(parts) + "."

    desc_raw = row.get("description")
    desc = str(desc_raw).strip() if desc_raw is not None else ""
    if desc:
        frag = _normalize_description_fragment(desc)
        core = f"{core} {frag}"

    url = _event_url_nonempty(row)
    if url:
        core = f"{core} [{name}]({url})"

    return core


def render_tier2_events(_query: str, rows: List[Dict[str, Any]]) -> str:
    """Render only ``type: event`` rows; caller must enforce dispatch."""
    if not rows:
        raise ValueError("render_tier2_events requires non-empty rows")

    sentences = [_render_one_event_sentence(r) for r in rows]
    n = len(sentences)

    if n == 1:
        return sentences[0]

    header = f"{n} events:"
    numbered = [f"{i + 1}. {sentences[i]}" for i in range(n)]
    core = header + _HEADER_BODY_SEPARATOR + "\n".join(numbered)
    framing = _event_list_framing_line(_query)
    return framing + _HEADER_BODY_SEPARATOR + core


def render_tier2_provider_cards_html(rows: list[dict[str, Any]]) -> str:
    """HTML snippet for commercial provider rows with favorite affordance.

    Each row must include ``entity_id``, ``slug``, and ``name``. Used by tests
    and reserved for a future deterministic HTML catalog path; the default chat
    Tier-2 path still uses the LLM formatter for non-all-event row sets.
    """
    if not rows:
        return ""
    parts: list[str] = []
    for row in rows:
        eid = str(row.get("entity_id") or "").strip()
        slug = str(row.get("slug") or "").strip()
        name = str(row.get("name") or "").strip()
        if not eid or not slug or not name:
            continue
        href = f"/provider/{html.escape(slug, quote=True)}"
        safe_name = html.escape(name, quote=False)
        parts.append(
            '<div class="tier2-catalog-card" style="margin:0.5rem 0;padding:0.75rem;'
            'border:1px solid #e5e7eb;border-radius:8px;display:flex;align-items:center;gap:0.5rem;">'
            f'<a href="{href}">{safe_name}</a>'
            f'<button type="button" class="favorite-heart" data-entity-id="{html.escape(eid, quote=True)}" '
            'aria-label="Save to favorites" title="Save">♥</button>'
            "</div>"
        )
    return "\n".join(parts)
