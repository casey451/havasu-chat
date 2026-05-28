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
from app.core.llm_messages import call_anthropic_messages

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    "* You're describing ONE THING (an event, a venue, or a business). The"
    " card with facts + actions renders BELOW your line — DO NOT enumerate"
    " hours, phone, address inline.\n"
    "* Lead with the why-it-matters / how-it-fits, not the what (the card"
    " shows the what).\n"
    "* No customer-service phrasing. No Southwest climate-as-texture.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)


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
    try:
        result = call_anthropic_messages(
            system_prompt=_SYSTEM_PROMPT,
            user_text=user_text,
            max_tokens=120,
            temperature=0.5,
        )
    except Exception:
        logger.exception("tier2_single_card: voice LLM raised; using fallback")
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
        logger.warning("tier2_single_card: voice contained '?'; using fallback")
        return fallback, in_tok, out_tok
    if len(text) > 280:
        logger.warning("tier2_single_card: voice too long; using fallback")
        return fallback, in_tok, out_tok

    return text, in_tok, out_tok


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
