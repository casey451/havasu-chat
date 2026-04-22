"""Tier 3 Haiku integration (Phase 3.2 — handoff §3.5 / §5).

``answer_with_tier3`` builds catalog context, calls Anthropic Messages API with
ephemeral prompt caching on the system block, and returns assistant text plus
total token usage for logging.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.chat.context_builder import build_context_for_tier3
from app.chat.intent_classifier import IntentResult
from app.chat.local_voice_matcher import find_matching_blurbs
from app.core.timezone import format_now_lake_havasu, now_lake_havasu

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
FALLBACK_MESSAGE = (
    "Something went sideways on my end — try that again in a sec, "
    "or call the business directly if you're in a hurry."
)
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
    inp_side, out_side = _split_usage(usage)
    return inp_side + out_side


def _split_usage(usage: object) -> tuple[int, int]:
    """Return (input-side billable tokens, output tokens). Cache reads/creates count as input."""
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cc = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return inp + cr + cc, out


def user_context_line_for_tier3(onboarding_hints: Mapping[str, Any] | None) -> str | None:
    """Comma-separated bias phrases for Tier 3 (not catalog facts). Omits line if nothing set."""
    if not onboarding_hints:
        return None
    parts: list[str] = []
    vs = onboarding_hints.get("visitor_status")
    if vs == "visiting":
        parts.append("visiting")
    elif vs == "local":
        parts.append("local")
    hk = onboarding_hints.get("has_kids")
    if hk is True:
        parts.append("with kids")
    elif hk is False:
        parts.append("no kids")
    age = onboarding_hints.get("age")
    if age is not None and age != "":
        parts.append(f"age {age}")
    loc = onboarding_hints.get("location")
    if isinstance(loc, str) and loc.strip():
        parts.append(loc.strip())
    if not parts:
        return None
    return "User context: " + ", ".join(parts) + "."


def compact_onboarding_user_context_line(
    onboarding_hints: Mapping[str, Any] | None,
) -> str | None:
    """Backward-compatible alias for tests / callers using the Phase 6.3 name."""
    return user_context_line_for_tier3(onboarding_hints)


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


def answer_with_tier3(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    onboarding_hints: Mapping[str, Any] | None = None,
    now_line: str | None = None,
) -> tuple[str, int | None, int | None, int | None]:
    """Return (assistant_text, total_tokens, llm_input_tokens, llm_output_tokens). Never raises."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier3: ANTHROPIC_API_KEY unset; graceful fallback")
        return FALLBACK_MESSAGE, None, None, None

    try:
        import anthropic
    except ImportError:
        logging.exception("tier3: anthropic package not installed")
        return FALLBACK_MESSAGE, None, None, None

    system_prompt = _load_system_prompt()
    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    context = build_context_for_tier3(query, intent_result, db)
    classifier_block = (
        f"Classifier: mode={intent_result.mode}, sub_intent={intent_result.sub_intent or 'none'}, "
        f"entity={intent_result.entity or 'none'}"
    )
    nl = (now_line or "").strip() or f"Now: {format_now_lake_havasu()}"
    if not nl.lower().startswith("now:"):
        nl = f"Now: {nl}"
    bias_line = user_context_line_for_tier3(onboarding_hints)
    mid_parts: list[str] = [classifier_block]
    if bias_line:
        mid_parts.append(bias_line)
    mid_parts.append(nl)
    mid = "\n\n".join(mid_parts)
    blurbs = find_matching_blurbs(
        query.strip(),
        onboarding_hints,
        now_lake_havasu().date(),
        max_results=3,
    )
    if blurbs:
        voice_lines: list[str] = []
        for b in blurbs:
            t = b.get("text")
            if isinstance(t, str) and t.strip():
                voice_lines.append(f"- {t.strip()}")
        if voice_lines:
            mid = f"{mid}\n\nLocal voice:\n" + "\n".join(voice_lines)
    user_text = f"User query:\n{query.strip()}\n\n{mid}\n\n{context}"

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
        return FALLBACK_MESSAGE, None, None, None

    text = _extract_text_from_message(msg)
    if not text:
        return FALLBACK_MESSAGE, None, None, None

    usage = getattr(msg, "usage", None)
    if usage is None:
        return text, None, None, None
    inp_side, out_side = _split_usage(usage)
    total = inp_side + out_side
    return text, total, inp_side, out_side
