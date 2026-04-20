"""Tier 2 orchestrator: parser → DB → formatter (Phase 4.2). Not wired into routing yet."""

from __future__ import annotations

import logging
from typing import Optional

from app.chat import tier2_db_query, tier2_formatter, tier2_parser

# Parser scores below this threshold skip Tier 2 and defer to Tier 3 (tunable in a later phase).
TIER2_CONFIDENCE_THRESHOLD = 0.7


def answer_with_tier2(query: str) -> Optional[str]:
    """Chain parser → DB query → formatter. Returns None to signal 'fall back to Tier 3'."""
    filters = tier2_parser.parse(query)
    if filters is None:
        logging.info("tier2_handler: fallback: parser error")
        return None
    if filters.fallback_to_tier3:
        logging.info("tier2_handler: fallback: parser refused")
        return None
    if filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD:
        logging.info("tier2_handler: fallback: low confidence")
        return None

    rows = tier2_db_query.query(filters)
    if len(rows) == 0:
        logging.info("tier2_handler: fallback: no matches")
        return None

    response = tier2_formatter.format(query, rows)
    if response is None:
        logging.info("tier2_handler: fallback: formatter error")
        return None

    return response
