"""Tier 2 query → structured filters (Phase 4.1). Import-only until routing (4.3)."""

from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic import ValidationError

from app.chat.tier2_schema import Tier2Filters
from app.core.llm_messages import (
    call_anthropic_messages,
    coerce_llm_text_to_json_object,
    load_prompt,
)

_MAX_OUTPUT_TOKENS = 300
_TEMPERATURE = 0.3


def parse(query: str) -> tuple[Optional[Tier2Filters], int | None, int | None]:
    """Parse a user query into Tier2Filters; returns (filters, input_tokens, output_tokens).

    On failure returns (None, None, None). Token counts are from the Anthropic usage object
    when the API call succeeds, even if JSON validation fails afterward.
    """
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier2_parser: ANTHROPIC_API_KEY unset")
        return None, None, None

    try:
        system_prompt = load_prompt("tier2_parser")
    except OSError:
        logging.exception("tier2_parser: failed to read parser system prompt")
        return None, None, None

    user_text = f"User query:\n{query.strip()}\n"

    result = call_anthropic_messages(
        system_prompt=system_prompt,
        user_text=user_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_TEMPERATURE,
        model=None,
    )
    if result is None:
        logging.error("tier2_parser: Anthropic messages.create failed")
        return None, None, None

    in_tok = result.usage.billable_input
    out_tok = result.usage.output_tokens

    try:
        parsed = coerce_llm_text_to_json_object(result.text)
        if parsed is None:
            logging.warning("tier2_parser: LLM output is not valid JSON")
            return None, in_tok, out_tok
        return Tier2Filters.model_validate(parsed), in_tok, out_tok
    except ValidationError:
        logging.warning("tier2_parser: JSON does not validate against Tier2Filters")
        return None, in_tok, out_tok
    except Exception:
        logging.exception("tier2_parser: unexpected error in parse")
        return None, in_tok, out_tok
