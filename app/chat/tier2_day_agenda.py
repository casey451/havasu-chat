"""Day-shape branch within Tier 2 (BUILD.md step 5 / task #12).

Called from ``tier2_handler.try_tier2_with_usage`` after parsing+querying.
When the query asks "what's happening on <day>" with multiple events,
this builds a structured ``day_agenda`` component + a short voice line —
instead of the existing formatter's long-prose output.

The detection is conservative (see ``component_builders.is_day_agenda_query``):
unusual filters or non-event-heavy result sets fall through to the
existing formatter.

Voice generation: an LLM call with a tight voice prompt, with a
deterministic fallback when the LLM is unavailable. Mirrors the
``app.home.pullquote`` SWR fallback discipline — never block on the LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.chat.component_builders import (
    build_day_agenda,
    fallback_day_agenda_voice,
    is_day_agenda_query,
    resolve_target_date,
)
from app.chat.tier2_schema import Tier2Filters
from app.core.llm_messages import call_anthropic_messages

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    "* No customer-service phrasing: never \"you might want to...\","
    " \"feel free to...\", \"I'd be happy to...\", \"here are several options\".\n"
    "* The structured listing renders BELOW your line — DO NOT enumerate items"
    " inline. Your job is the read on the day, not a roll call.\n"
    "* No Southwest climate-as-texture (\"monsoon\", \"dry heat\").\n"
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided. Never"
    " invent venues or URLs.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)


def try_build_day_agenda(
    query: str,
    filters: Tier2Filters,
    rows: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], int, int] | None:
    """Try to build a day_agenda component for the query.

    Returns (voice, component_data, llm_input_tokens, llm_output_tokens) on
    success; None when the query shape doesn't match. Token counts are 0
    when the deterministic fallback voice was used (no LLM call).

    Caller passes the parser+DB-query results so we don't redo that work
    when the shape doesn't match.
    """
    if not is_day_agenda_query(filters, rows):
        return None

    component_data = build_day_agenda(filters, rows)
    voice, v_in, v_out = _generate_voice(query, rows, filters)
    return voice, component_data, v_in, v_out


# ─────────── voice generation ───────────


def _generate_voice(
    query: str,
    rows: list[dict[str, Any]],
    filters: Tier2Filters,
) -> tuple[str, int, int]:
    """Short voice line. LLM when available, deterministic fallback otherwise.

    Returns (voice, input_tokens, output_tokens). Token counts are 0 when
    the fallback was used.
    """
    target = resolve_target_date(filters)
    fallback = fallback_day_agenda_voice(rows, target)

    user_text = _build_user_prompt(query, rows, target)
    try:
        result = call_anthropic_messages(
            system_prompt=_SYSTEM_PROMPT,
            user_text=user_text,
            max_tokens=120,
            temperature=0.5,
        )
    except Exception:
        logger.exception("tier2_day_agenda: voice LLM raised; using fallback")
        return fallback, 0, 0

    if result is None or not (result.text or "").strip():
        return fallback, 0, 0

    text = result.text.strip()
    # Defensive: drop wrapping quotes if the LLM added them.
    if (text.startswith(('"', "'", "“", "”")) and text.endswith(('"', "'", "“", "”"))
            and len(text) > 1):
        text = text[1:-1].strip()

    in_tok = result.usage.billable_input or 0
    out_tok = result.usage.output_tokens or 0

    # Voice rule guards. If any fail, use the fallback (better to be
    # deterministic and on-voice than off-voice).
    if "?" in text:
        logger.warning("tier2_day_agenda: voice contained '?'; using fallback")
        return fallback, in_tok, out_tok
    if len(text) > 280:
        logger.warning("tier2_day_agenda: voice too long; using fallback")
        return fallback, in_tok, out_tok

    return text, in_tok, out_tok


def _build_user_prompt(
    query: str, rows: list[dict[str, Any]], target: Any
) -> str:
    target_label = (
        target.strftime("%A, %B ") + str(target.day) if hasattr(target, "strftime") else str(target)
    )
    summary_lines: list[str] = []
    for r in rows[:8]:  # cap at 8 to keep the prompt tight
        name = r.get("name") or ""
        venue = r.get("location_name") or ""
        time = r.get("start_time") or ""
        url = (r.get("event_url") or "").strip()
        line = f"- {name}"
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
        f"Day: {target_label}\n"
        f"Rows on this day ({len(rows)} total):\n{rows_block}\n\n"
        "Write Hava's read on the day. 1–2 sentences. The structured list"
        " renders below; do not enumerate items inline."
    )
