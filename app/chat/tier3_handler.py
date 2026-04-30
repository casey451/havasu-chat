"""Tier 3 Haiku integration (Phase 3.2 — handoff §3.5 / §5).

``answer_with_tier3`` builds catalog context, calls Anthropic Messages API with
ephemeral prompt caching on the system block, and returns assistant text plus
total token usage for logging.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.chat.context_builder import build_context_for_tier3
from app.chat.intent_classifier import IntentResult
from app.chat.local_voice_matcher import find_matching_blurbs
from app.core.llm_messages import anthropic, call_anthropic_messages, load_prompt
from app.core.timezone import format_now_lake_havasu, now_lake_havasu

FALLBACK_MESSAGE = (
    "Something went sideways on my end — try that again in a sec, "
    "or call the business directly if you're in a hurry."
)
_MAX_OUTPUT_TOKENS = 150
_TEMPERATURE = 0.3

_INLINE_SYSTEM_PROMPT_FALLBACK = (
    "You are a Lake Havasu City concierge. Answer in 1–3 short sentences, "
    "contractions, no filler, no follow-up questions. Use only the Context block for facts."
)


def _load_tier3_system_prompt() -> str:
    """Tier3-specific graceful fallback on missing prompt file.

    Stays at call site per decision doc §Findings: tier3's graceful fallback is
    intentional behavior, not boilerplate.
    """
    try:
        return load_prompt("system_prompt")
    except OSError:
        return _INLINE_SYSTEM_PROMPT_FALLBACK


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

    if anthropic is None:
        logging.error("tier3: anthropic package not installed")
        return FALLBACK_MESSAGE, None, None, None

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

    result = call_anthropic_messages(
        system_prompt=_load_tier3_system_prompt(),
        user_text=user_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_TEMPERATURE,
        model=None,
    )
    if result is None:
        logging.error("tier3: Anthropic messages.create failed")
        return FALLBACK_MESSAGE, None, None, None

    if not result.text:
        return FALLBACK_MESSAGE, None, None, None

    usage = getattr(result.raw, "usage", None)
    if usage is None:
        return result.text, None, None, None

    inp_side = result.usage.billable_input
    out_side = result.usage.output_tokens
    total = inp_side + out_side
    return result.text, total, inp_side, out_side
