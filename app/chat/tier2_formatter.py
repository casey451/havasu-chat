"""Tier 2 response formatting from catalog rows (Phase 4.2). Import-only until routing."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_MAX_OUTPUT_TOKENS = 400
_TEMPERATURE = 0.3


def _load_formatter_system_prompt() -> str:
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / "tier2_formatter.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"tier2 formatter prompt missing: {path}")


def _extract_text_from_message(msg: object) -> str:
    parts: list[str] = []
    content = getattr(msg, "content", None) or []
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "text":
            t = getattr(block, "text", "") or ""
            if t:
                parts.append(t)
    return " ".join(parts).strip()


def _usage_in_out(msg: object) -> tuple[int | None, int | None]:
    usage = getattr(msg, "usage", None)
    if usage is None:
        return None, None
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cc = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return inp + cr + cc, out


def format(query: str, rows: List[Dict[str, Any]]) -> tuple[Optional[str], int | None, int | None]:
    """Render DB rows into a response. Returns (text, input_tokens, output_tokens)."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier2_formatter: ANTHROPIC_API_KEY unset")
        return None, None, None

    try:
        import anthropic
    except ImportError:
        logging.exception("tier2_formatter: anthropic package not installed")
        return None, None, None

    try:
        system_prompt = _load_formatter_system_prompt()
    except OSError:
        logging.exception("tier2_formatter: failed to read formatter system prompt")
        return None, None, None

    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    rows_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    user_text = (
        f"Query: {query.strip()}\n\n"
        f"Catalog rows:\n{rows_json}\n\n"
        "Respond:"
    )
    model = (os.getenv("ANTHROPIC_MODEL") or "").strip() or DEFAULT_MODEL

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=_TEMPERATURE,
            system=system_blocks,
            messages=[{"role": "user", "content": user_text}],
        )
    except Exception:
        logging.exception("tier2_formatter: Anthropic messages.create failed")
        return None, None, None

    try:
        text = _extract_text_from_message(msg)
        in_tok, out_tok = _usage_in_out(msg)
        if not text:
            logging.warning("tier2_formatter: empty model response")
            return None, in_tok, out_tok
        if in_tok is not None:
            logging.info("tier2_formatter: tokens in=%s out=%s", in_tok, out_tok)
        return text, in_tok, out_tok
    except Exception:
        logging.exception("tier2_formatter: unexpected error in format")
        return None, None, None
