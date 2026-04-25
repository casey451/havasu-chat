"""Tier 2 orchestrator: parser → DB → formatter (Phase 4.2). Wired from router in Phase 4.3."""

from __future__ import annotations

import logging
from typing import Optional

from app.chat import tier2_db_query, tier2_formatter, tier2_parser
from app.chat.tier2_schema import Tier2Filters

# Parser scores below this threshold skip Tier 2 and defer to Tier 3 (tunable in a later phase).
TIER2_CONFIDENCE_THRESHOLD = 0.7


def try_tier2_with_usage(
    query: str,
) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """Return (response_text, llm_tokens_used, llm_input_tokens, llm_output_tokens).

    On full success, ``llm_tokens_used`` is parser+formatter totals; on fallback ``text`` is
    ``None`` and token fields are ``None``.
    """
    q = (query or "").strip()
    if not q:
        logging.info("tier2_handler: fallback: empty query")
        return None, None, None, None

    filters, p_in, p_out = tier2_parser.parse(q)
    if filters is None:
        logging.info("tier2_handler: fallback: parser error")
        return None, None, None, None
    if filters.fallback_to_tier3:
        logging.info("tier2_handler: fallback: parser refused")
        return None, None, None, None
    if filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD:
        logging.info("tier2_handler: fallback: low confidence")
        return None, None, None, None

    rows = tier2_db_query.query(filters)
    if len(rows) == 0:
        logging.info("tier2_handler: fallback: no matches")
        return None, None, None, None

    text, f_in, f_out = tier2_formatter.format(q, rows)
    if text is None:
        logging.info("tier2_handler: fallback: formatter error")
        return None, None, None, None

    pi, po = (p_in or 0), (p_out or 0)
    fi, fo = (f_in or 0), (f_out or 0)
    in_sum = pi + fi
    out_sum = po + fo
    total = in_sum + out_sum
    return text, total, in_sum, out_sum


def answer_with_tier2(query: str) -> Optional[str]:
    """Chain parser → DB query → formatter. Returns None to signal 'fall back to Tier 3'."""
    text, _, _, _ = try_tier2_with_usage(query)
    return text


def try_tier2_with_filters_with_usage(
    query: str, filters: Tier2Filters
) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """Run Tier 2 using precomputed filters (skip parser).

    Returns the same tuple shape as :func:`try_tier2_with_usage`.
    """
    q = (query or "").strip()
    if not q:
        logging.info("tier2_handler: fallback: empty query")
        return None, None, None, None
    if filters.fallback_to_tier3:
        logging.info("tier2_handler: fallback: router filters marked fallback_to_tier3")
        return None, None, None, None
    if filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD:
        logging.info("tier2_handler: fallback: router filters low confidence")
        return None, None, None, None

    rows = tier2_db_query.query(filters)
    if len(rows) == 0:
        logging.info("tier2_handler: fallback: no matches")
        return None, None, None, None

    text, f_in, f_out = tier2_formatter.format(q, rows)
    if text is None:
        logging.info("tier2_handler: fallback: formatter error")
        return None, None, None, None

    in_sum = f_in or 0
    out_sum = f_out or 0
    total = in_sum + out_sum
    return text, total, in_sum, out_sum
