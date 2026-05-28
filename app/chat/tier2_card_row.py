"""Card-row branch within Tier 2 (BUILD.md step 5 Phase 5B).

Called from tier2_handler after parser+DB. When the query asks for a curated
short list of recommendations ("date night", "good spots for X"), this
builds a structured card_row component + short voice instead of long prose.
Same SWR discipline as tier2_day_agenda / tier2_week_strip: LLM call with
tight prompt + deterministic fallback. Never block on the LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.chat.component_builders import (
    build_card_row,
    fallback_card_row_voice,
    is_card_row_query,
)
from app.chat.tier2_schema import Tier2Filters
from app.core.llm_messages import call_anthropic_messages

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    "* You're framing 2–3 hand-picked recommendations — give the read on the"
    " shape of the picks (e.g. 'Both lean upscale.' 'One waterfront, one"
    " patio.'). The cards render BELOW your line — DO NOT enumerate them"
    " inline. DO NOT list names.\n"
    "* No customer-service phrasing: never 'you might want to...', 'feel free"
    " to...', 'I'd be happy to...', 'here are several options'.\n"
    "* No Southwest climate-as-texture ('monsoon', 'dry heat').\n"
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided. Never"
    " invent venues or URLs.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)


def try_build_card_row(
    query: str,
    filters: Tier2Filters,
    rows: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], int, int] | None:
    """Try to build a card_row component. Returns (voice, data, in_tok, out_tok) or None.

    Same contract as tier2_week_strip.try_build_week_strip — when the shape
    doesn't match, return None and let the existing formatter run.
    """
    if not is_card_row_query(query, filters, rows):
        return None

    component_data = build_card_row(filters, rows)
    voice, v_in, v_out = _generate_voice(query, rows)
    return voice, component_data, v_in, v_out


def _generate_voice(
    query: str,
    rows: list[dict[str, Any]],
) -> tuple[str, int, int]:
    fallback = fallback_card_row_voice(rows, query)

    user_text = _build_user_prompt(query, rows)
    try:
        result = call_anthropic_messages(
            system_prompt=_SYSTEM_PROMPT,
            user_text=user_text,
            max_tokens=120,
            temperature=0.5,
        )
    except Exception:
        logger.exception("tier2_card_row: voice LLM raised; using fallback")
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
        logger.warning("tier2_card_row: voice contained '?'; using fallback")
        return fallback, in_tok, out_tok
    if len(text) > 280:
        logger.warning("tier2_card_row: voice too long; using fallback")
        return fallback, in_tok, out_tok

    return text, in_tok, out_tok


def _build_user_prompt(
    query: str,
    rows: list[dict[str, Any]],
) -> str:
    summary_lines: list[str] = []
    for r in rows[:3]:
        name = r.get("name") or ""
        category = (
            r.get("google_primary_category")
            or r.get("category")
            or r.get("activity_category")
            or ""
        )
        venue = r.get("location_name") or r.get("address") or ""
        line = f"- {name}"
        if category:
            line += f" ({category})"
        if venue:
            line += f", {venue}"
        summary_lines.append(line)
    rows_block = "\n".join(summary_lines) or "(no rows)"
    return (
        f"User asked: {query}\n\n"
        f"Rows in this result ({len(rows)} total):\n{rows_block}\n\n"
        "Write Hava's read on these picks. 1–2 sentences. The mini-cards"
        " render below; do not enumerate items inline."
    )
