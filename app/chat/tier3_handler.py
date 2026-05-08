"""Tier 3 LLM synthesis integration (Phase 3.2 — handoff §3.5 / §5).

``answer_with_tier3`` builds catalog context, calls OpenAI chat.completions
(``gpt-4o-mini`` by default; OpenAI handles prompt caching automatically),
and returns assistant text plus total token usage for logging.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.chat.context_builder import build_context_for_tier3
from app.chat.intent_classifier import IntentResult
from app.chat.llm_cache import lookup as cache_lookup, make_cache_key, store as cache_store
from app.chat.local_voice_matcher import find_matching_blurbs
from app.chat.tier3_postprocess import strip_soft_suggest
from app.core.llm_messages import call_anthropic_messages, load_prompt
from app.core.timezone import format_now_lake_havasu, now_lake_havasu

FALLBACK_MESSAGE = (
    "Something went sideways on my end — try that again in a sec, "
    "or call the business directly if you're in a hurry."
)
_MAX_OUTPUT_TOKENS = 150
_TEMPERATURE = 0.3

# Stream C, lever B (2026-05-08): Tier 3 synthesis uses ``gpt-4.1-mini`` for
# stricter voice discipline. ``gpt-4o-mini`` produces customer-service drift
# on synthesis queries even with strong system prompts; the bigger model
# follows instructions more reliably. Tier 2 parser/formatter and
# ``hint_extractor`` stay on the cheaper default — those are extraction tasks
# where 4o-mini is fine. Per-call cost goes up ~3x ($0.15 → $0.40 per million
# input tokens, $0.60 → $1.60 per million output) — at 5K Tier 3 queries/month
# that's ~$3–5 added baseline, mostly absorbed by the response cache once
# steady state hit rate climbs. Override via ``TIER3_MODEL`` env var for
# emergency rollback to 4o-mini without a code change.
_TIER3_MODEL = (os.getenv("TIER3_MODEL") or "").strip() or "gpt-4.1-mini"

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
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier3: OPENAI_API_KEY unset; graceful fallback")
        return FALLBACK_MESSAGE, None, None, None

    # Stream C, lever Cache (2026-05-08): check the LLM response cache before
    # spending tokens. Cache key = normalized_query + context_hash + rubric
    # version hash. Hits return zero-token responses; misses fall through to
    # the LLM call which writes the response back into the cache.
    cache_context: dict[str, Any] = {}
    if onboarding_hints:
        for k in ("visitor_status", "has_kids", "age", "location"):
            v = onboarding_hints.get(k)
            if v is not None and v != "":
                cache_context[k] = v
    # today's date in catalog timezone — so "this weekend" doesn't bleed
    # across the week boundary on cache hits
    cache_context["_today"] = now_lake_havasu().date().isoformat()
    cache_key = make_cache_key(query, cache_context)
    # §4.3 (cache v2): pass the normalized query so cache_lookup can fall back
    # to embedding-similarity matching when the exact-key path misses. Cost
    # of the embedding API call (~$0.00001/query) is dominated by the Tier 3
    # synthesis it might save (~$0.001/query); ROI is fine even at modest
    # similarity-hit rates.
    cached_response = cache_lookup(db, cache_key, normalized_query=query)
    if cached_response:
        logging.info("tier3: cache hit (key=%s)", cache_key[:8])
        # Cache hit returns zero tokens — chat_logs will reflect this. Filter
        # ``llm_input_tokens = 0 AND tier_used = 'tier3'`` to count cache hits.
        return cached_response, 0, 0, 0

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
        model=_TIER3_MODEL,
    )
    if result is None:
        logging.error("tier3: OpenAI chat.completions.create failed")
        return FALLBACK_MESSAGE, None, None, None

    if not result.text:
        return FALLBACK_MESSAGE, None, None, None

    # Voice-battery 2026-05-08 (Stream C, lever E): strip soft-suggest
    # customer-service phrasing the LLM occasionally produces despite the
    # system prompt's explicit ban. Deterministic, runs once per response,
    # never raises. See app/chat/tier3_postprocess.py for rule details.
    cleaned_text = strip_soft_suggest(result.text)
    if not cleaned_text:
        cleaned_text = result.text  # defensive: never return empty

    # Stream C, lever Cache: write the response into the cache for future
    # identical queries. Default 7-day TTL; rubric-version-hashed key auto-
    # invalidates when prompts change. Failures are swallowed by store().
    cache_store(
        db,
        cache_key,
        query,
        cache_context,
        cleaned_text,
        tier_used="tier3",
    )

    usage = getattr(result.raw, "usage", None)
    if usage is None:
        return cleaned_text, None, None, None

    inp_side = result.usage.billable_input
    out_side = result.usage.output_tokens
    total = inp_side + out_side
    return cleaned_text, total, inp_side, out_side
