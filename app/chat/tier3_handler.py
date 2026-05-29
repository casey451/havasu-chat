"""Tier 3 LLM synthesis integration (Phase 3.2 -- handoff sec 3.5 / 5).

``answer_with_tier3`` builds catalog context, calls OpenAI chat.completions
(``gpt-4o-mini`` by default; OpenAI handles prompt caching automatically),
and returns assistant text plus total token usage for logging.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Mapping, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

from app.chat import disclosure_render
from app.chat.chat_request_context import ChatRequestContext
from app.chat.context_builder import (
    build_context_and_rows_for_tier3,
    rows_for_tier3_classification,
)
from app.chat.intent_classifier import IntentResult
from app.chat.llm_cache import lookup_with_embedding as cache_lookup_with_embedding
from app.chat.llm_cache import make_cache_key
from app.chat.llm_cache import store_with_embedding as cache_store_with_embedding
from app.chat.local_voice_matcher import find_matching_blurbs
from app.chat.tier2_formatter import (
    _enforce_low_tier_phone,
    is_confidence_tier_enabled,
)
from app.chat.tier3_postprocess import strip_soft_suggest
from app.core.llm_messages import call_anthropic_messages, load_prompt
from app.core.timezone import format_now_lake_havasu, now_lake_havasu
from app.db.database import SessionLocal
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


def _store_cache_in_background(
    db_sessionmaker,
    cache_key: str,
    query: str,
    cache_context: dict,
    text_for_cache: str,
    precomputed_embedding: list[float] | None,
) -> None:
    """Best-effort cache write. Runs after the response has returned."""
    import sentry_sdk

    sentry_sdk.add_breadcrumb(
        category="cache.store",
        message="llm_cache.store_with_embedding (deferred)",
        data={"cache_key_prefix": cache_key[:8], "has_embedding": precomputed_embedding is not None},
        level="info",
    )
    logging.info(
        "llm_cache.store_background.start key=%s has_embed=%s",
        cache_key[:8],
        precomputed_embedding is not None,
    )
    try:
        with db_sessionmaker() as bg_db:
            cache_store_with_embedding(
                bg_db,
                cache_key,
                query,
                cache_context,
                text_for_cache,
                tier_used="tier3",
                precomputed_embedding=precomputed_embedding,
            )
        logging.info("llm_cache.store_background.ok key=%s", cache_key[:8])
    except Exception:
        sentry_sdk.capture_exception()
        logging.exception("llm_cache.store_background.fail key=%s", cache_key[:8])


def _tier3_components_enabled() -> bool:
    """BUILD.md step 5 Phase 5E feature flag. Off by default."""
    v = (os.getenv("HAVA_TIER3_COMPONENTS") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _apply_tier3_component_probe(
    component_meta: dict[str, Any] | None,
    intent_result: IntentResult,
    tier3_rows: list[dict[str, Any]],
) -> None:
    """Post-LLM deterministic single_card / single_business_card overlay."""
    if component_meta is None or not _tier3_components_enabled():
        return
    entity = (intent_result.entity or "").strip()
    if not entity:
        return
    try:
        from app.chat.component_builders import (
            build_single_business_card,
            build_single_card,
            is_single_business_card_query,
            is_single_card_query,
            pick_single_entity_row,
        )

        if is_single_business_card_query(intent_result, tier3_rows):
            row = pick_single_entity_row(entity, tier3_rows, row_types=("provider",))
            if row is not None:
                component_meta["type"] = "single_business_card"
                component_meta["data"] = build_single_business_card(intent_result, row)
        elif is_single_card_query(intent_result, tier3_rows):
            row = pick_single_entity_row(entity, tier3_rows, row_types=("event",))
            if row is not None:
                component_meta["type"] = "single_card"
                component_meta["data"] = build_single_card(intent_result, row)
    except Exception:
        logging.exception("tier3: component_meta probe failed")


# Tier 3's voice prompt lives at prompts/system_prompt.txt and is loaded
# verbatim to enable Anthropic prompt-cache hits — it is intentionally
# NOT routed through app.chat.voice_principles. The brand source of
# truth (BUILD.md §"Voice principles") is mirrored independently in
# both surfaces. See voice_principles.py module docstring for the
# boundary rationale.


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
        return disclosure_render.render_with_decision(
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
    chat_ctx: ChatRequestContext | None = None,
    background_tasks: "BackgroundTasks | None" = None,
    telemetry: dict | None = None,
    component_meta: Optional[dict[str, Any]] = None,
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
    t_lookup_start = time.perf_counter()
    cached_response, precomputed_embedding = cache_lookup_with_embedding(
        db, cache_key, normalized_query=query
    )
    lookup_ms = int((time.perf_counter() - t_lookup_start) * 1000)
    if telemetry is not None:
        telemetry["tier3_lookup_ms"] = lookup_ms
        if cached_response is not None:
            telemetry["cache_status"] = (
                "hit_exact" if precomputed_embedding is None else "hit_sim"
            )
        else:
            telemetry["cache_status"] = "miss"
        if precomputed_embedding is not None:
            telemetry["tier3_embed_ran"] = True

    request_ctx = chat_ctx or ChatRequestContext()
    context, tier3_rows = build_context_and_rows_for_tier3(
        query, intent_result, db, chat_ctx=request_ctx
    )

    if cached_response:
        logging.info("tier3: cache hit (key=%s)", cache_key[:8])
        # BUILD.md step 5 Phase 5E: component_meta is intentionally NOT in the
        # cache key — voice text is cached; structured component is re-derived
        # from tier3_rows on every call (hit or miss). Rows stay fresh via
        # build_context_and_rows_for_tier3 above even when voice is cached.
        cleaned_text = cached_response
        if is_confidence_tier_enabled():
            rows_hit = rows_for_tier3_classification(intent_result, db)
            cleaned_text = _enforce_low_tier_phone(cleaned_text, rows_hit)
        _apply_tier3_component_probe(component_meta, intent_result, tier3_rows)
        if sponsored_block is not None:
            cleaned_text = _inject_sponsored_block(cleaned_text, sponsored_block)
        return cleaned_text, 0, 0, 0

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
    for preamble in request_ctx.tier3_context_preambles():
        mid_parts.append(preamble)
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

    t_llm_start = time.perf_counter()
    result = call_anthropic_messages(
        system_prompt=_load_tier3_system_prompt(),
        user_text=user_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_TEMPERATURE,
        model=_TIER3_MODEL,
    )
    if telemetry is not None:
        telemetry["tier3_llm_ms"] = int((time.perf_counter() - t_llm_start) * 1000)
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

    _apply_tier3_component_probe(component_meta, intent_result, tier3_rows)

    # component_meta is intentionally NOT in the cache key — voice text only.
    if background_tasks is not None:
        background_tasks.add_task(
            _store_cache_in_background,
            SessionLocal,
            cache_key,
            query,
            cache_context,
            text_for_cache,
            precomputed_embedding,
        )
    else:
        cache_store_with_embedding(
            db,
            cache_key,
            query,
            cache_context,
            text_for_cache,
            tier_used="tier3",
            precomputed_embedding=precomputed_embedding,
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
