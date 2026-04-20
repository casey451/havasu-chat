"""Tier 3 Haiku integration (Phase 3.2 — handoff §3.5 / §5).

``answer_with_tier3`` builds catalog context, calls Anthropic Messages API with
ephemeral prompt caching on the system block, and returns assistant text plus
total token usage for logging.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.chat.context_builder import build_context_for_tier3
from app.chat.intent_classifier import IntentResult

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
FALLBACK_MESSAGE = "Something went sideways on my end — try that again in a sec."
_MAX_OUTPUT_TOKENS = 150
_TEMPERATURE = 0.3


def _load_system_prompt() -> str:
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / "system_prompt.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return (
        "You are a Lake Havasu City concierge. Answer in 1–3 short sentences, "
        "contractions, no filler, no follow-up questions. Use only the Context block for facts."
    )


def _sum_usage(usage: object) -> int:
    """Sum billable input + output + cache-related tokens from Anthropic usage object."""
    if usage is None:
        return 0
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cc = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return inp + out + cr + cc


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


def answer_with_tier3(query: str, intent_result: IntentResult, db: Session) -> tuple[str, int | None]:
    """Return (assistant_text, total_tokens_or_None). Never raises to callers."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier3: ANTHROPIC_API_KEY unset; graceful fallback")
        return FALLBACK_MESSAGE, None

    try:
        import anthropic
    except ImportError:
        logging.exception("tier3: anthropic package not installed")
        return FALLBACK_MESSAGE, None

    system_prompt = _load_system_prompt()
    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    context = build_context_for_tier3(query, intent_result, db)
    user_text = (
        f"User query:\n{query.strip()}\n\n"
        f"Classifier: mode={intent_result.mode}, sub_intent={intent_result.sub_intent or 'none'}, "
        f"entity={intent_result.entity or 'none'}\n\n"
        f"{context}"
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
        logging.exception("tier3: Anthropic messages.create failed")
        return FALLBACK_MESSAGE, None

    text = _extract_text_from_message(msg)
    if not text:
        return FALLBACK_MESSAGE, None

    usage = getattr(msg, "usage", None)
    if usage is None:
        return text, None
    return text, _sum_usage(usage)
