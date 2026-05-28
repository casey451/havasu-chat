"""Week-shape branch within Tier 2 (BUILD.md step 5 Phase 5A).

Called from tier2_handler after parser+DB. When the query asks "what's on
this week" / "what's next week" with several events, builds a structured
week_strip component + short voice. Same SWR discipline as tier2_day_agenda:
LLM call with tight prompt + deterministic fallback.
"""

from __future__ import annotations

import logging
from typing import Any

from app.chat.component_builders import (
    build_week_strip,
    fallback_week_strip_voice,
    is_week_strip_query,
    resolve_week_window,
)
from app.chat.tier2_schema import Tier2Filters
from app.core.llm_messages import call_anthropic_messages

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    "* You're describing the WEEK as a whole (N things across the week, busy"
    " days vs quiet ones, one or two stand-outs). The 7-day strip + selected-day"
    " agenda renders BELOW your line — DO NOT enumerate items inline.\n"
    "* No customer-service phrasing.\n"
    "* No Southwest climate-as-texture.\n"
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)


def try_build_week_strip(
    query: str,
    filters: Tier2Filters,
    rows: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], int, int] | None:
    """Try to build a week_strip component. Returns (voice, data, in_tok, out_tok) or None.

    Same contract as tier2_day_agenda.try_build_day_agenda — when the shape
    doesn't match, return None and let the existing formatter run.
    """
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
    try:
        result = call_anthropic_messages(
            system_prompt=_SYSTEM_PROMPT,
            user_text=user_text,
            max_tokens=120,
            temperature=0.5,
        )
    except Exception:
        logger.exception("tier2_week_strip: voice LLM raised; using fallback")
        return fallback, 0, 0

    if result is None or not (result.text or "").strip():
        return fallback, 0, 0

    text = result.text.strip()
    if (text.startswith(('"', "'", "“", "”")) and text.endswith(('"', "'", "“", "”"))
            and len(text) > 1):
        text = text[1:-1].strip()

    in_tok = result.usage.billable_input or 0
    out_tok = result.usage.output_tokens or 0

    if "?" in text:
        logger.warning("tier2_week_strip: voice contained '?'; using fallback")
        return fallback, in_tok, out_tok
    if len(text) > 280:
        logger.warning("tier2_week_strip: voice too long; using fallback")
        return fallback, in_tok, out_tok

    return text, in_tok, out_tok


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
