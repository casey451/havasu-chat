"""Week-shape branch within Tier 2 (BUILD.md step 5 Phase 5A).

Called from tier2_handler after parser+DB. When the query asks "what's on
this week" / "what's next week" with several events, builds a structured
week_strip component + short voice. Same SWR discipline as tier2_day_agenda:
LLM call with tight prompt + deterministic fallback.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.chat.component_builders import (
    build_week_strip,
    fallback_week_strip_voice,
    is_week_strip_query,
    resolve_week_window,
)
from app.chat.tier2_schema import Tier2Filters
from app.chat.voice_principles import compose_voice_prompt, run_voice_llm

logger = logging.getLogger(__name__)

# P1-2: the week_strip is an event-calendar component, but is_week_strip_query keys
# only on filters + row counts. A non-event question that happens to acquire a
# week-window filter and event rows (e.g. a "things to do" intent defaulting to a
# 7-day window — "what should I do when it's too hot") wrongly renders a 7-day event
# strip. Require an explicit event / temporal-event signal in the user's text before
# the strip can fire. Conservative: phrases like "what's on this week", "things to do
# this weekend", "events tonight" all match; "what should I do when it's too hot" does
# not. Mirrors the discipline of is_week_strip_query (when in doubt, fall through).
_EVENT_INTENT_RE = re.compile(
    r"\b(events?|happening|going on|what'?s\s+on|things?\s+to\s+do|to\s+do|"
    r"calendar|agenda|line\s?up|festivals?|fairs?|concerts?|live\s+music|"
    r"shows?|tonight|today|this\s+week|next\s+week|this\s+weekend|weekend|"
    r"schedule)\b",
    re.IGNORECASE,
)


def _query_has_event_intent(query: str) -> bool:
    """True when the user's text actually asks about events / what's-on."""
    return bool(_EVENT_INTENT_RE.search(query or ""))


def try_build_week_strip(
    query: str,
    filters: Tier2Filters,
    rows: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], int, int] | None:
    """Try to build a week_strip component. Returns (voice, data, in_tok, out_tok) or None.

    Same contract as tier2_day_agenda.try_build_day_agenda — when the shape
    doesn't match, return None and let the existing formatter run.
    """
    # P1-2: don't render an event calendar for a non-event question, even if the
    # filters scoped a week window and the result set is event-heavy.
    if not _query_has_event_intent(query):
        return None
    if not is_week_strip_query(filters, rows):
        return None

    component_data = build_week_strip(filters, rows)
    voice, v_in, v_out = _generate_voice(query, rows, filters)
    return voice, component_data, v_in, v_out


def _generate_voice(
    query: str,
    rows: list[dict[str, Any]],
    filters: Tier2Filters,
) -> tuple[str, int, int]:
    window = resolve_week_window(filters)
    fallback = fallback_week_strip_voice(rows, window)
    user_text = _build_user_prompt(query, rows, window)
    return run_voice_llm(
        system_prompt=compose_voice_prompt("week_strip"),
        user_text=user_text,
        fallback_text=fallback,
        logger=logger,
        surface="tier2_week_strip",
    )


def _build_user_prompt(
    query: str,
    rows: list[dict[str, Any]],
    window: tuple[Any, Any],
) -> str:
    start, end = window
    window_label = (
        f"{start.strftime('%b ')}{start.day} – {end.strftime('%b ')}{end.day}"
        if hasattr(start, "strftime")
        else f"{start} – {end}"
    )
    summary_lines: list[str] = []
    for r in rows[:12]:
        name = r.get("name") or ""
        day = r.get("date") or ""
        venue = r.get("location_name") or ""
        time = r.get("start_time") or ""
        url = (r.get("event_url") or "").strip()
        line = f"- {name}"
        if day:
            line += f" ({day})"
        if time:
            line += f" at {time}"
        if venue:
            line += f", {venue}"
        if url:
            line += f"  ({url})"
        summary_lines.append(line)
    rows_block = "\n".join(summary_lines) or "(no rows)"
    return (
        f"User asked: {query}\n\n"
        f"Week: {window_label}\n"
        f"Rows in this window ({len(rows)} total):\n{rows_block}\n\n"
        "Write Hava's read on the week. 1–2 sentences. The 7-day strip and"
        " selected-day agenda render below; do not enumerate items inline."
    )
