"""Single-entity branch within Tier 2 (BUILD.md step 5 Phase 5C).

Called from tier2_handler after parser+DB. When the query names a single
catalog entity and asks "tell me about it" (rather than a factual lookup
that Tier 1 owns), builds a structured single_card / single_business_card
component + short voice. Same SWR discipline as tier2_day_agenda /
tier2_week_strip: LLM call with tight prompt + deterministic fallback.

The JS renderer aliases single_business_card to renderSingleCard (one
renderer for both); the backend keeps two builders because the payloads
populate different fields (status pill, recent_review for businesses).
"""

from __future__ import annotations

import logging
from typing import Any

from app.chat.component_builders import (
    build_single_business_card,
    build_single_card,
    fallback_single_card_voice,
    is_single_business_card_query,
    is_single_card_query,
    pick_single_entity_row,
)
from app.chat.intent_classifier import IntentResult
from app.chat.tier2_schema import Tier2Filters
from app.chat.voice_principles import compose_voice_prompt, run_voice_llm

logger = logging.getLogger(__name__)


def try_build_single_card(
    query: str,
    intent_result: IntentResult,
    filters: Tier2Filters,
    rows: list[dict[str, Any]],
) -> tuple[str, str, dict[str, Any], int, int] | None:
    """Try to build a single_card / single_business_card component.

    Returns (component_type, voice, data, in_tok, out_tok) or None.
    component_type is "single_card" or "single_business_card" — the
    caller writes it into component_meta["type"] verbatim.

    When the shape doesn't match, returns None and lets the existing
    formatter run.
    """
    del filters
    is_business = is_single_business_card_query(intent_result, rows)
    is_event = is_single_card_query(intent_result, rows)
    if not is_business and not is_event:
        return None

    entity = (intent_result.entity or "").strip()
    if is_business:
        row = pick_single_entity_row(entity, rows, row_types=("provider",))
        if row is None:
            return None
        component_type = "single_business_card"
        component_data = build_single_business_card(intent_result, row)
    else:
        row = pick_single_entity_row(entity, rows, row_types=("event",))
        if row is None:
            return None
        component_type = "single_card"
        component_data = build_single_card(intent_result, row)

    voice, v_in, v_out = _generate_voice(query, row, is_business=is_business)
    return component_type, voice, component_data, v_in, v_out


def _generate_voice(
    query: str,
    row: dict[str, Any],
    *,
    is_business: bool,
) -> tuple[str, int, int]:
    fallback = fallback_single_card_voice(row, is_business=is_business)
    user_text = _build_user_prompt(query, row, is_business=is_business)
    kind = "single_business_card" if is_business else "single_card"
    return run_voice_llm(
        system_prompt=compose_voice_prompt(kind),
        user_text=user_text,
        fallback_text=fallback,
        logger=logger,
        surface=f"tier2_{kind}",
    )


def _build_user_prompt(
    query: str,
    row: dict[str, Any],
    *,
    is_business: bool,
) -> str:
    name = row.get("name") or ""
    category = (
        row.get("google_primary_category")
        or row.get("category")
        or row.get("activity_category")
        or ""
    )
    summary = row.get("description") or row.get("featured_description") or ""
    kind = "business" if is_business else "event/venue"
    return (
        f"User asked: {query}\n\n"
        f"Catalog {kind}: {name}\n"
        f"Category: {category}\n"
        f"Summary: {summary}\n\n"
        "Write Hava's read on this one thing. 1–2 sentences. The card with"
        " facts and actions renders below; do not enumerate details inline."
    )
