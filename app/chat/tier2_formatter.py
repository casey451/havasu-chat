"""Tier 2 response formatting from catalog rows (Phase 4.2). Import-only until routing."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from app.chat import tier2_catalog_render
from app.core.llm_messages import call_anthropic_messages, load_prompt

_MAX_OUTPUT_TOKENS = 400
_TEMPERATURE = 0.3

EMPTY_CATALOG_MESSAGE = "No matching catalog rows."

_LEGACY_FALLBACK_RE = re.compile(
    r"\bImported from River Scene\. Event URL:\s*\S+\s*",
    re.IGNORECASE,
)


def _strip_legacy_fallback(description: str | None) -> str:
    """Strip legacy River Scene import scaffolding from ``Event.description``.

    Pre-commit-1 ingestion wrote this prefix when HTML body prose was empty.
    After backfill apply, rows should not match; kept as a safety net.
    """
    if not description:
        return description or ""
    return _LEGACY_FALLBACK_RE.sub("", description, count=1).strip()


def _format_via_llm(query: str, rows: List[Dict[str, Any]]) -> tuple[Optional[str], int | None, int | None]:
    """Anthropic-backed formatting for mixed or non-event catalog rows."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier2_formatter: ANTHROPIC_API_KEY unset")
        return None, None, None

    try:
        system_prompt = load_prompt("tier2_formatter")
    except OSError:
        logging.exception("tier2_formatter: failed to read formatter system prompt")
        return None, None, None

    rows_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    user_text = (
        f"Query: {query.strip()}\n\n"
        f"Catalog rows:\n{rows_json}\n\n"
        "Respond:"
    )

    result = call_anthropic_messages(
        system_prompt=system_prompt,
        user_text=user_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_TEMPERATURE,
        model=None,
    )
    if result is None:
        logging.error("tier2_formatter: Anthropic messages.create failed")
        return None, None, None

    if not result.text:
        logging.warning("tier2_formatter: empty model response")
        return None, result.usage.billable_input, result.usage.output_tokens

    in_tok = result.usage.billable_input
    out_tok = result.usage.output_tokens
    if getattr(result.raw, "usage", None) is not None:
        logging.info("tier2_formatter: tokens in=%s out=%s", in_tok, out_tok)
    return result.text, in_tok, out_tok


def format(query: str, rows: List[Dict[str, Any]]) -> tuple[Optional[str], int | None, int | None]:
    """Render DB rows into a response. Returns (text, input_tokens, output_tokens).

    Empty ``rows`` and all-``event`` rows use deterministic paths (0 formatter tokens).
    """
    rows = [
        {**r, "description": _strip_legacy_fallback(r.get("description"))}
        if "description" in r
        else r
        for r in rows
    ]

    if not rows:
        return EMPTY_CATALOG_MESSAGE, 0, 0

    if all(r.get("type") == "event" for r in rows):
        try:
            text = tier2_catalog_render.render_tier2_events(query, rows)
            if not (text or "").strip():
                logging.warning("tier2_formatter: deterministic render returned empty")
                return None, None, None
            return text.strip(), 0, 0
        except Exception:
            logging.exception("tier2_formatter: deterministic render failed")
            return None, None, None

    return _format_via_llm(query, rows)
