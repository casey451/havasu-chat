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
from app.chat.voice_principles import compose_voice_prompt, run_voice_llm

logger = logging.getLogger(__name__)


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
    return run_voice_llm(
        system_prompt=compose_voice_prompt("card_row"),
        user_text=user_text,
        fallback_text=fallback,
        logger=logger,
        surface="tier2_card_row",
    )


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
