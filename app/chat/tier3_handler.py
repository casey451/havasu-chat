"""Tier 3 LLM synthesis integration (Phase 3.2 -- handoff sec 3.5 / 5).

``answer_with_tier3`` builds catalog context, calls OpenAI chat.completions
(``gpt-4o-mini`` by default; OpenAI handles prompt caching automatically),
and returns assistant text plus total token usage for logging.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.chat import disclosure_render
from app.chat.context_builder import (
    build_context_for_tier3,
    rows_for_tier3_classification,
)
from app.chat.intent_classifier import IntentResult
from app.chat.llm_cache import lookup as cache_lookup
from app.chat.llm_cache import make_cache_key
from app.chat.llm_cache import store as cache_store
from app.chat.local_voice_matcher import find_matching_blurbs
from app.chat.tier2_formatter import (
    _enforce_low_tier_phone,
    is_confidence_tier_enabled,
)
from app.chat.tier3_postprocess import strip_soft_suggest
from app.core.llm_messages import call_anthropic_messages, load_prompt
from app.core.timezone import format_now_lake_havasu, now_lake_havasu
from app.db.models import Sponsor, SponsorStatus

FALLBACK_MESSAGE = (
    "Something went sideways on my end — try that again in a sec, "
    "or call the business directly if you're in a hurry."
)
_MAX_OUTPUT_TOKENS = 150
_TEMPERATURE = 0.3

# Stream C, lever B (2026-05-08): Tier 3 synthesis uses ``gpt-4.1-mini`` for
# stricter voice discipline. Per-call cost goes up ~3x; absorbed by cache.
# Override via ``TIER3_MODEL`` env var for emergency rollback to 4o-mini
# without a code change.
_TIER3_MODEL = (os.getenv("TIER3_MODEL") or "").strip() or "gpt-4.1-mini"

_INLINE_SYSTEM_PROMPT_FALLBACK = (
    "You are a Lake Havasu City concierge. Answer in 1-3 short sentences, "
    "contractions, no filler, no follow-up questions. Use only the Context block for facts."
)


def _load_tier3_system_prompt() -> str:
    """Tier3-specific graceful fallback on missing prompt file."""
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
    """Backward-compatible alias."""
    return user_context_line_for_tier3(onboarding_hints)


def _format_sponsored_block(block: disclosure_render.SponsoredBlock) -> str:
    """Render a SponsoredBlock as a single-line string for chat injection."""
    line = f"{block.disclosure_word}: {block.attribution}. {block.body}"
    if block.cta:
        line = f"{line} {block.cta}"
    if not line.endswith("."):
        line = f"{line}."
    return line


def _inject_sponsored_block(
    text: str, block: disclosure_render.SponsoredBlock
) -> str:
    """Place a sponsored block in the response text per regime."""
    rendered = _format_sponsored_block(block)
    if block.regime == disclosure_render.PlacementRegime.EMERGENCY_URGENT:
        return f"{rendered}\n\n{text}".strip()
    first_period = text.find(".")
    if first_period == -1:
        return f"{text} {rendered}".strip()
    head = text[: first_period + 1]
    tail = text[first_period + 1 :]
    return f"{head} {rendered}{tail}"


def _maybe_render_sponsored_block(
    intent_result: IntentResult,
    db: Session,
    *,
    organic_rows: Optional[list[Mapping[str, Any]]] = None,
    category: Optional[str] = None,
) -> Optional[disclosure_render.SponsoredBlock]:
    """Compute a SponsoredBlock or return None -- never raises."""
    try:
        regime = disclosure_render.select_placement_regime(intent_result)
        if regime == disclosure_render.PlacementRegime.SPECIFIC_QUALITY:
            return None
        now = now_lake_havasu()
        candidates: list[Sponsor] = (
            db.query(Sponsor)
            .filter(
                Sponsor.status == SponsorStatus.LIVE.value,
                Sponsor.active.is_(True),
                or_(Sponsor.starts_at.is_(None), Sponsor.starts_at <= now),
                or_(Sponsor.ends_at.is_(None), Sponsor.ends_at > now),
            )
            .all()
        )
        if not candidates:
            return None
        return disclosure_render.render_sponsored_block(
            regime=regime,
            candidate_sponsors=candidates,
            query_context={
                "organic_rows": list(organic_rows or []),
                "category": category,
                "date_context": now,
            },
            db=db,
        )
    except Exception as exc:  # noqa: BLE001 -- renderer must never break chat
        logging.warning(
            "tier3: disclosure renderer raised (%s); falling through to LLM-only path",
            exc,
        )
        return None


def answer_with_tier3(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    onboarding_hints: Mapping[str, Any] | None = None,
    now_line: str | None = None,
    organic_context: Optional[list[Mapping[str, Any]]] = None,
) -> tuple[str, int | None, int | None, int | None]:
    """Return (assistant_text, total_tokens, llm_input_tokens, llm_output_tokens). Never raises."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier3: OPENAI_API_KEY unset; graceful fallback")
        return FALLBACK_MESSAGE, None, None, None

    sponsored_block: Optional[disclosure_render.SponsoredBlock] = None
    if disclosure_render.is_renderer_enabled():
        sponsored_block = _maybe_render_sponsored_block(
            intent_result,
            db,
            organic_rows=organic_context,
            category=getattr(intent_result, "inferred_category", None),
        )

    cache_context: dict[str, Any] = {}
    if onboarding_hints:
        for k in ("visitor_status", "has_kids", "age", "location"):
            v = onboarding_hints.get(k)
            if v is not None and v != "":
                cache_context[k] = v
    cache_context["_today"] = now_lake_havasu().date().isoformat()
    cache_key = make_cache_key(query, cache_context)
    cached_response = cache_lookup(db, cache_key, normalized_query=query)
    if cached_response:
        logging.info("tier3: cache hit (key=%s)", cache_key[:8])
        if is_confidence_tier_enabled():
            rows_hit = rows_for_tier3_classification(intent_result, db)
            cached_response = _enforce_low_tier_phone(cached_response, rows_hit)
        if sponsored_block is not None:
            cached_response = _inject_sponsored_block(cached_response, sponsored_block)
        return cached_response, 0, 0, 0

    context = build_context_for_tier3(query, intent_result, db)
    sub_intent_str = intent_result.sub_intent or "none"
    entity_str = intent_result.entity or "none"
    classifier_block = (
        f"Classifier: mode={intent_result.mode}, sub_intent={sub_intent_str}, "
        f"entity={entity_str}"
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

    cleaned_text = strip_soft_suggest(result.text)
    if not cleaned_text:
        cleaned_text = result.text  # defensive: never return empty

    text_for_cache = cleaned_text
    # Lane CT2.B.1 (Backlog #42): post-LLM phone enforcement on the Tier 3
    # path. Mirrors the Tier 2 backstop in ``tier2_formatter.format`` --
    # when a LOW-tier provider has a phone but the LLM omitted both the
    # number and the canonical hedge, append the deterministic call-to-
    # confirm fragment. Sibling helper returns the row list backing the
    # context block (single shared query, no timing skew). Behind the
    # confidence-tier feature flag -- off in production until rollout.
    # Backlog #49: cache stores raw LLM output (post strip_soft_suggest only);
    # ``_enforce_low_tier_phone`` runs on miss and again on cache hit so flag
    # flips and post-processor edits apply without stale hedge text in Redis/DB.
    if is_confidence_tier_enabled():
        rows = rows_for_tier3_classification(intent_result, db)
        cleaned_text = _enforce_low_tier_phone(cleaned_text, rows)

    cache_store(
        db,
        cache_key,
        query,
        cache_context,
        text_for_cache,
        tier_used="tier3",
    )

    if sponsored_block is not None:
        cleaned_text = _inject_sponsored_block(cleaned_text, sponsored_block)

    usage = getattr(result.raw, "usage", None)
    if usage is None:
        return cleaned_text, None, None, None

    inp_side = result.usage.billable_input
    out_side = result.usage.output_tokens
    total = inp_side + out_side
    return cleaned_text, total, inp_side, out_side
