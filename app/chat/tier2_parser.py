"""Tier 2 query → structured filters (Phase 4.1). Import-only until routing (4.3)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from app.chat.tier2_schema import Tier2Filters

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_MAX_OUTPUT_TOKENS = 300
_TEMPERATURE = 0.3


def _load_parser_system_prompt() -> str:
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / "tier2_parser.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"tier2 parser prompt missing: {path}")


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


def _coerce_llm_text_to_json_object(raw: str) -> Optional[dict[str, Any]]:
    """Return a dict parsed from model text, or None if the payload is not a JSON object."""
    s = raw.strip()
    if not s:
        return None
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl == -1:
            return None
        inner = s[first_nl + 1 :]
        fence = inner.rfind("```")
        if fence != -1:
            inner = inner[:fence]
        s = inner.strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _usage_in_out(msg: object) -> tuple[int | None, int | None]:
    usage = getattr(msg, "usage", None)
    if usage is None:
        return None, None
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cc = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return inp + cr + cc, out


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
        import anthropic
    except ImportError:
        logging.exception("tier2_parser: anthropic package not installed")
        return None, None, None

    try:
        system_prompt = _load_parser_system_prompt()
    except OSError:
        logging.exception("tier2_parser: failed to read parser system prompt")
        return None, None, None

    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user_text = f"User query:\n{query.strip()}\n"
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
        logging.exception("tier2_parser: Anthropic messages.create failed")
        return None, None, None

    in_tok, out_tok = _usage_in_out(msg)

    try:
        text = _extract_text_from_message(msg)
        data = _coerce_llm_text_to_json_object(text)
        if data is None:
            logging.warning("tier2_parser: LLM output is not valid JSON")
            return None, in_tok, out_tok
        return Tier2Filters.model_validate(data), in_tok, out_tok
    except ValidationError:
        logging.warning("tier2_parser: JSON does not validate against Tier2Filters")
        return None, in_tok, out_tok
    except Exception:
        logging.exception("tier2_parser: unexpected error in parse")
        return None, in_tok, out_tok
