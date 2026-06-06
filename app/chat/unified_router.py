"""Unified concierge router (Phase 2.2 — handoff §3.2, §5 Phase 2.2).

Orchestrates normalize → classify → entity enrichment → mode handler → log.
Ask uses Tier 1 when applicable, else Tier 3 (Anthropic); contribute uses zero-token
intake templates (Stream B 2026-05-07), correct uses zero-token correction template,
chat uses real short responses (§8).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Mapping
from uuid import uuid4

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

from sqlalchemy import or_ as _sa_or
from sqlalchemy.orm import Session

from app.chat import disclosure_render, llm_router
from app.chat.audience_signal import AudienceSignal, classify_audience
from app.chat.chat_request_context import ChatRequestContext, parse_chat_request_context
from app.chat.entity_matcher import (
    ensure_entity_matcher,
    extract_catalog_entities_from_text,
    match_entity,
)
from app.chat.hint_extractor import extract_hints
from app.chat.intent_classifier import IntentResult, classify
from app.chat.normalizer import normalize
from app.chat.tier1_handler import (
    render_contribute_template,
    render_correction_template,
    try_tier1,
)
from app.chat.tier2_handler import (
    try_tier2_with_filters_with_usage,
    try_tier2_with_usage,
)
from app.chat.tier3_handler import FALLBACK_MESSAGE as _GRACEFUL
from app.chat.tier3_handler import answer_with_tier3
from app.core.conditions_temperature import read_current_temperature_f
from app.core.session import (
    OnboardingHints,
    PriorEntity,
    SessionState,
    get_session,
    record_entity,
    touch_session,
    update_hints_from_extraction,
)
from app.core.timezone import format_now_lake_havasu, now_lake_havasu
from app.db.chat_logging import log_unified_route

_PRONOUN_REFERENT = re.compile(
    r"\b(it|that|there|they|them|the place|that place)\b",
    re.IGNORECASE,
)

_EXPLICIT_REC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat should i do\b", re.IGNORECASE),
    re.compile(r"\bpick one\b", re.IGNORECASE),
    re.compile(r"\bwhich is best\b", re.IGNORECASE),
    re.compile(r"\bbest\b", re.IGNORECASE),
    re.compile(r"\bworth it\b", re.IGNORECASE),
    re.compile(r"\byour favorite\b", re.IGNORECASE),
    re.compile(r"\bwhat would you do\b", re.IGNORECASE),
)

_GREETINGS: tuple[str, ...] = (
    "Heya.",
    "Hey.",
    "Hey, good to see you.",
)

_OUT_OF_SCOPE_REPLY = (
    "That's outside what I cover right now — I stick to things-to-do, local businesses, and events. "
    "Want me to point you to anything else?"
)


_GAP_TAIL = "Add it at /contribute or share the name and a link (Google Business page or official site) — either works."

# Slice F3: extend the gap-template path to every Tier 1 factual sub_intent so a
# missing-entity factual lookup gets a structured zero-token reply instead of falling
# through to the LLM. AGE/COST/DATE keep the program/event-shaped copy below.
_GAP_TIER1_FACTUAL = frozenset(
    {
        "PHONE_LOOKUP",
        "WEBSITE_LOOKUP",
        "RATING_LOOKUP",
        "REVIEW_COUNT_LOOKUP",
        "TIME_LOOKUP",
        "OPEN_NOW",
        "HOURS_LOOKUP",
        "LOCATION_LOOKUP",
        "DATE_LOOKUP",
        "AGE_LOOKUP",
        "COST_LOOKUP",
        "NEXT_OCCURRENCE",
    }
)

_UNKNOWN_ENTITY_GAP = (
    "I don't have that one in the catalog. "
    "If it's a real Lake Havasu business, share the name plus a URL "
    "(Google Business page or official site) and I'll pass it along — "
    "or add it at /contribute."
)

# Phase 7.5.3 F5: optional lead-in clause before about-gate patterns.
# Captures "Hey, ", "Quick question — ", "OK, so ", etc. (punctuation-anchored).
_LEAD_IN_PREFIX = r"^\s*(?:[a-z][a-z\s,'-]{0,40}[,—\-]\s+)?"

# Always gate — unambiguous "about a named entity" shapes (q07 primary).
_ABOUT_GATE_STRICT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_LEAD_IN_PREFIX + r"tell\s+me\s+(?:more\s+)?about\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"(?:can\s+you\s+)?describe\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"who(?:'s|\s+is)\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"(?:any\s+)?info(?:rmation)?\s+(?:on|about)\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"what(?:'s|\s+is)\s+\S+\s+like\b", re.I),
)

# Broader "what is X" — only when X is not activity/listing phrasing (Phase 7.5.1).
_WHAT_IS_ENTITY_RE = re.compile(
    _LEAD_IN_PREFIX + r"what(?:'s|\s+is)\s+(?!the\s+weather|the\s+time|the\s+date|today)",
    re.I,
)

_ACTIVITY_OR_LISTING_SKIP_RE = re.compile(
    r"\b(?:"
    r"fun|to\s+do|weekend|tonight|best\s+thing|should\s+we|"
    r"at\s+the|open\s+(?:now|right\s+now)"
    r")\b",
    re.I,
)


def _about_gate_query_eligible(raw: str) -> bool:
    """True when the query should enter _unknown_entity_about_gate."""
    if any(p.search(raw) for p in _ABOUT_GATE_STRICT_PATTERNS):
        return True
    if _WHAT_IS_ENTITY_RE.search(raw):
        return not bool(_ACTIVITY_OR_LISTING_SKIP_RE.search(raw))
    return False


# Queries that LOOK like Tier 1 factual lookups but are actually recommendation /
# listing shapes — gap response would be misleading ("I don't have that place"). These
# need to fall through to Tier 2/3.
_RECOMMENDATION_SHAPED = re.compile(
    # Slice F bug fix: dropped "what are some|the" — it false-matched factual questions
    # like "what are the hours for X" (asking for one specific entity's hours, gap-eligible).
    # The listing shortcut handles legitimate "what are some restaurants" cases.
    r"^\s*("
    r"where\s+should\s+(?:i|we)|"
    r"where\s+can\s+(?:i|we)\s+find|"
    r"where\s+can\s+(?:i|we)\s+get|"
    # 2026-06-04: rent/hire/book/charter are recommendation shapes too -- "where can
    # i rent a boat" was falling into the single-entity near-match gap path and
    # answering with one provider's street address.
    r"where\s+can\s+(?:i|we)\s+(?:rent|hire|book|charter)|"
    r"where\s+do\s+(?:i|we)\s+(?:rent|hire|book|charter)|"
    r"what\s+should\s+(?:i|we)|"
    r"what(?:'s|\s+is)\s+a\s+good|"
    r"best\s+(?:place|spot|restaurant|cafe|bar)|"
    r"good\s+(?:place|spot|restaurant|cafe|bar)"
    r")\b",
    re.IGNORECASE,
)


def _catalog_gap_response(intent_result: IntentResult, db: Session | None = None) -> str | None:
    """Tier 1-shaped fact lookup with no catalog entity — template only, no Tier 3.

    Slice F3 extends this from the original three intents (DATE/LOCATION/HOURS) to all
    Tier 1 factual sub_intents with intent-tailored copy. Safeguards skip the gap path
    when the query is recommendation-shaped, listing-shaped, OR (Slice F §3.2) when
    the query maps to multiple ambiguous catalog entities — those should defer to
    Tier 3 for disambiguation, not show "/contribute" copy.
    """
    sub = intent_result.sub_intent
    raw = intent_result.raw_query or ""
    if re.search(r"\bwait(?:\s+time)?\b", raw, re.I):
        return f"I don't have live wait-time data in the catalog yet. {_GAP_TAIL}"
    if sub not in _GAP_TIER1_FACTUAL:
        return None
    if (intent_result.entity or "").strip():
        return None
    if _RECOMMENDATION_SHAPED.match(raw):
        return None
    # Also defer to Tier 2 listing shortcut — if the query matches that shape, the
    # Tier 2 path will produce a real listing response (or fall through itself).
    try:
        from app.chat.tier2_business_shortcut import try_business_listing_shortcut

        if try_business_listing_shortcut(raw) is not None:
            return None
    except Exception:
        logging.exception("_catalog_gap_response: shortcut probe failed")

    try:
        from app.chat.entity_intent import is_category_open_now_listing

        if is_category_open_now_listing(raw):
            return None
    except Exception:
        logging.exception("_catalog_gap_response: category-open-now probe failed")

    # NOTE (Slice F §3.2 reverted): the gap-skip-on-ambiguity check was disabled
    # after a prod regression — with 2,266 providers, the ambiguity probe over-fires
    # on background score noise, causes gap to skip, and the request falls into the
    # Tier 2/3 LLM path which still has unresolved API issues on prod. The
    # entity_matcher's ambiguity flag is still computed; we just don't act on it here
    # until the matcher's stricter scoring or a deterministic disambiguation reply
    # lands. See `tests/voice_battery/reports/final_report.md` §3.2.

    # Slice F: when the query has a near-miss canonical (typo / partial name that
    # didn't clear the 75 threshold), try to answer the user's original question
    # using the near match as the entity. If Tier 1 can produce an answer for the
    # near-match provider, return it with a "Looks like you might mean ..." prefix —
    # the user gets their answer AND knows we disambiguated. Falls back to a plain
    # "closest match" reply when Tier 1 can't render (e.g. no phone for that row).
    if db is not None:
        try:
            from dataclasses import replace as _dc_replace

            from app.chat.entity_matcher import find_near_match
            from app.chat.tier1_handler import try_tier1

            near = find_near_match(raw, db)
            if near is not None:
                near_name, _score = near
                from app.chat.entity_intent import near_match_subject_overlaps

                if not near_match_subject_overlaps(raw, near_name):
                    near = None
            if near is not None:
                near_name, _score = near
                boosted_ir = _dc_replace(intent_result, entity=near_name)
                tier1_resp = try_tier1(raw, boosted_ir, db)
                if tier1_resp:
                    # Answer first (Tier 1 response already names the entity), then
                    # a soft escape hatch — no yes/no question, no doubled name.
                    return (
                        f"{tier1_resp} If you meant a different place, "
                        f"/contribute can add the right listing."
                    )
                return (
                    f"Closest match in the catalog is {near_name}. "
                    f"Ask again with that name, or /contribute can add a different listing."
                )
        except Exception:
            logging.exception("_catalog_gap_response: near-match probe failed")

    if sub in ("HOURS_LOOKUP", "OPEN_NOW", "TIME_LOOKUP"):
        return f"I don't have those hours in the catalog yet. {_GAP_TAIL}"
    if sub == "LOCATION_LOOKUP":
        return f"I don't have that place in the catalog yet. {_GAP_TAIL}"
    if sub == "PHONE_LOOKUP":
        return f"I don't have that business's phone in the catalog yet. {_GAP_TAIL}"
    if sub == "WEBSITE_LOOKUP":
        return f"I don't have a website for that one in the catalog yet. {_GAP_TAIL}"
    if sub in ("RATING_LOOKUP", "REVIEW_COUNT_LOOKUP"):
        return f"I don't have Google reviews for that one in the catalog yet. {_GAP_TAIL}"
    # AGE/COST/DATE/NEXT_OCCURRENCE — program/event-shaped copy.
    return f"I don't have that event or program in the catalog yet. {_GAP_TAIL}"


def _unknown_entity_about_gate(
    query: str,
    intent_result: IntentResult,
    db: Session | None = None,
) -> str | None:
    """Pre-tier-3 gate: 'tell me about X' patterns with no catalog match
    short-circuit to a deterministic gap template, never invoking tier-3 LLM.

    q07 fix 2026-05-19. Returns the gap string when the pattern fires; None
    otherwise (caller proceeds with normal _handle_ask flow).
    """
    raw = (query or "").strip()
    if not _about_gate_query_eligible(raw):
        return None
    if (intent_result.entity or "").strip():
        return None  # we have a real entity — let tier 1/2/3 handle it

    try:
        from app.chat.entity_intent import (
            near_match_subject_overlaps,
            query_mentions_fake_entity_marker,
        )
        from app.chat.entity_matcher import find_near_match, match_entity

        if db is not None:
            ensure_entity_matcher(db)
            if match_entity(raw, db) is not None:
                return None
            near = find_near_match(raw, db)
            if near is not None and near_match_subject_overlaps(raw, near[0]):
                return None  # plausible "did you mean" — defer to existing path

        # Phase 7.5.3 F1: marker probe runs AFTER matcher + near-match so the
        # consonant-run heuristic cannot regress legitimate typo near-matches
        # like "mdshrkbrwry" -> Mudshark Brewery (rapidfuzz in
        # near_match_subject_overlaps must take precedence).
        if query_mentions_fake_entity_marker(raw):
            return _UNKNOWN_ENTITY_GAP
    except Exception:
        logging.exception("_unknown_entity_about_gate: matcher probe failed")
        return None

    return _UNKNOWN_ENTITY_GAP


@dataclass
class ChatResponse:
    response: str
    mode: str
    sub_intent: str | None
    entity: str | None
    tier_used: str  # '1' | '2' | '3' | 'gap_template' | 'intake' | 'correction' | 'chat' | 'placeholder' | 'track_a' (historical chat_logs rows only; no current emitter)
    latency_ms: int
    llm_tokens_used: int | None = None
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    chat_log_id: str | None = None
    # BUILD.md step 5: voice + component split. Defaults preserve existing
    # behavior — `voice` mirrors `response`, component is "none" (voice-only
    # rendering). Real component payloads land per query shape in steps 6+.
    voice: str = ""
    component_type: str = "none"
    component_data: dict = field(default_factory=dict)
    # Slice 0: True when the intent layer already wrote the query_log row for
    # this turn, so the HTTP layer's logger skips (one query_log row per turn).
    intent_logged: bool = False


def _stable_session_bucket(session_id: str | None) -> str:
    if session_id and session_id.strip():
        return session_id.strip()[:128]
    return uuid4().hex[:24]


def _greeting_variant(session_id: str | None) -> str:
    key = (session_id or "__anon__").encode("utf-8")
    idx = int(hashlib.sha256(key).hexdigest(), 16) % len(_GREETINGS)
    return _GREETINGS[idx]


def _is_explicit_rec(query: str) -> bool:
    """Detect §8.4 explicit recommendation triggers with word boundaries."""
    if not query:
        return False
    return any(p.search(query) for p in _EXPLICIT_REC_PATTERNS)


def _use_llm_router() -> bool:
    v = (os.environ.get("USE_LLM_ROUTER") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _organic_context_for_tier3(
    intent_result: IntentResult, db: Session, *, limit: int = 5
) -> list[Mapping[str, Any]] | None:
    """Build organic-row context for the disclosure renderer (Backlog #40 wiring).

    Lane X2 added an ``organic_context`` kwarg on ``answer_with_tier3`` so the
    renderer's ``EMERGENCY_URGENT`` regime can verify organic alternatives
    exist before injecting a sponsored block (spec §1.3). Phase 1 callers
    didn't populate it; this helper is the X2.1 wiring.

    Returns ``None`` (cheap, kwarg becomes a no-op) when:
    - the disclosure renderer feature flag is off (renderer is never invoked);
    - the regime resolves to anything other than ``EMERGENCY_URGENT``
      (renderer doesn't read ``organic_rows`` for ``GENERIC_CATEGORY`` /
      ``SPECIFIC_QUALITY``);
    - the normalized query yields no usable keywords;
    - the Provider lookup raises or returns an empty result set.

    Otherwise returns up to ``limit`` Provider dicts whose ``provider_name``
    or ``category`` overlaps a ≥4-char keyword from the normalized query.
    Best-effort: any failure returns ``None``, which suppresses the
    sponsored block — the safe failure mode for paid placements.
    """
    if not disclosure_render.is_renderer_enabled():
        return None
    try:
        regime = disclosure_render.select_placement_regime(intent_result)
    except Exception:
        logging.exception("unified_router: regime lookup failed")
        return None
    if regime != disclosure_render.PlacementRegime.EMERGENCY_URGENT:
        return None

    nq = (intent_result.normalized_query or "").lower().strip()
    if not nq:
        return None
    keywords = [w for w in re.split(r"\W+", nq) if len(w) >= 4]
    if not keywords:
        return None

    try:
        from app.db.models import Provider

        clauses: list[Any] = []
        for w in keywords:
            clauses.append(Provider.provider_name.ilike(f"%{w}%"))
            clauses.append(Provider.category.ilike(f"%{w}%"))
        rows = (
            db.query(Provider)
            .filter(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                _sa_or(*clauses),
            )
            .limit(limit)
            .all()
        )
    except Exception:
        logging.exception("unified_router: organic-context Provider query failed")
        return None

    if not rows:
        return None
    return [
        {
            "type": "provider",
            "id": p.id,
            "provider_name": p.provider_name,
            "category": p.category,
        }
        for p in rows
    ]


def _build_chat_request_context(
    intent_result: IntentResult,
    *,
    request_headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    preferred_mode: str | None = None,
) -> ChatRequestContext:
    base = parse_chat_request_context(
        headers=request_headers,
        query_params=query_params,
        preferred_mode=preferred_mode,
    )
    multi = intent_result.multi_domain_category_slugs
    if multi:
        return ChatRequestContext(
            boat_mode=base.boat_mode,
            temperature_f=base.temperature_f,
            multi_domain_category_slugs=multi,
        )
    return base


def _handle_ask(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    onboarding_hints: OnboardingHints | None = None,
    now_line: str | None = None,
    allow_tier3_fallback: bool = True,
    router_meta: dict | None = None,
    component_meta: dict | None = None,
    chat_ctx: ChatRequestContext | None = None,
    background_tasks: "BackgroundTasks | None" = None,
    telemetry: dict[str, Any] | None = None,
) -> tuple[str | None, str, int | None, int | None, int | None]:
    t_t1_start = time.perf_counter()
    tier1 = try_tier1(query, intent_result, db)
    if tier1 is not None:
        if telemetry is not None:
            telemetry["cache_status"] = "bypass"
            telemetry["tier1_ms"] = int((time.perf_counter() - t_t1_start) * 1000)
        return tier1, "1", None, None, None
    # Ask Hava intent layer (flag-gated; USE_INTENT_LAYER off by default). Sits
    # at the front of Tier 2: a confident rule/slot match answers from the
    # catalog with no LLM call and logs the intent to query_log. Anything else
    # returns None and falls through to the existing Tier 2 / Tier 3 path
    # unchanged. Best-effort -- any failure falls through.
    try:
        from app.chat.intents.runtime import try_intent_layer

        intent_answer = try_intent_layer(
            query,
            db,
            entity=intent_result.entity,
            sub_intent=intent_result.sub_intent,
            telemetry=telemetry,
        )
    except Exception:
        logging.exception("unified_router: intent layer failed")
        intent_answer = None
    if intent_answer is not None:
        if telemetry is not None:
            telemetry["cache_status"] = "bypass"
            telemetry["intent_key"] = intent_answer.intent_key
        if component_meta is not None and intent_answer.component_type != "none":
            component_meta["type"] = intent_answer.component_type
            component_meta["data"] = intent_answer.component_data
        return intent_answer.text, "2", None, None, None
    if _use_llm_router():
        context: dict[str, object] = {}
        if onboarding_hints:
            context["onboarding_hints"] = onboarding_hints
        if now_line:
            context["now_line"] = now_line
        if (intent_result.entity or "").strip():
            context["prior_entity"] = intent_result.entity
        decision = llm_router.route(query, intent_result.normalized_query, context or None)
        if decision is None:
            # Backlog #40: capture organic context for the renderer's
            # EMERGENCY_URGENT regime; helper returns None when the flag
            # is off or the regime doesn't need pairing — kwarg is a no-op.
            organic_ctx = _organic_context_for_tier3(intent_result, db)
            text, total, tin, tout = answer_with_tier3(
                query,
                intent_result,
                db,
                onboarding_hints=onboarding_hints,
                now_line=now_line,
                organic_context=organic_ctx,
                chat_ctx=chat_ctx,
                background_tasks=background_tasks,
                telemetry=telemetry,
                component_meta=component_meta,
            )
            return text, "3", total, tin, tout
        if router_meta is not None:
            router_meta["mode"] = decision.mode
            router_meta["sub_intent"] = decision.sub_intent
            router_meta["entity"] = decision.entity
        routed_intent = replace(
            intent_result,
            mode=decision.mode,
            sub_intent=decision.sub_intent,
            entity=decision.entity,
        )
        if decision.tier_recommendation == "2" and decision.tier2_filters is not None:
            t2_text, t2_total, t2_in, t2_out = try_tier2_with_filters_with_usage(
                query,
                decision.tier2_filters,
                component_meta=component_meta,
                chat_ctx=chat_ctx,
                telemetry=telemetry,
                intent_result=routed_intent,
            )
            if t2_text is not None:
                return t2_text, "2", t2_total, t2_in, t2_out
            if not allow_tier3_fallback:
                return None, "placeholder", None, None, None
            organic_ctx = _organic_context_for_tier3(routed_intent, db)
            text, total, tin, tout = answer_with_tier3(
                query,
                routed_intent,
                db,
                onboarding_hints=onboarding_hints,
                now_line=now_line,
                organic_context=organic_ctx,
                chat_ctx=chat_ctx,
                background_tasks=background_tasks,
                telemetry=telemetry,
                component_meta=component_meta,
            )
            return text, "3", total, tin, tout
        organic_ctx = _organic_context_for_tier3(routed_intent, db)
        text, total, tin, tout = answer_with_tier3(
            query,
            routed_intent,
            db,
            onboarding_hints=onboarding_hints,
            now_line=now_line,
            organic_context=organic_ctx,
            chat_ctx=chat_ctx,
            background_tasks=background_tasks,
            telemetry=telemetry,
            component_meta=component_meta,
        )
        return text, "3", total, tin, tout
    if _is_explicit_rec(query):
        from app.chat.entity_intent import infer_listing_category_term

        if infer_listing_category_term(query):
            t2_cat, t2_total, t2_in, t2_out = try_tier2_with_usage(
                query,
                component_meta=component_meta,
                chat_ctx=chat_ctx,
                telemetry=telemetry,
                intent_result=intent_result,
            )
            if t2_cat is not None:
                return t2_cat, "2", t2_total, t2_in, t2_out
        organic_ctx = _organic_context_for_tier3(intent_result, db)
        text, total, tin, tout = answer_with_tier3(
            query,
            intent_result,
            db,
            onboarding_hints=onboarding_hints,
            now_line=now_line,
            organic_context=organic_ctx,
            chat_ctx=chat_ctx,
            background_tasks=background_tasks,
            telemetry=telemetry,
            component_meta=component_meta,
        )
        return text, "3", total, tin, tout
    t2_text, t2_total, t2_in, t2_out = try_tier2_with_usage(
        query,
        component_meta=component_meta,
        chat_ctx=chat_ctx,
        telemetry=telemetry,
        intent_result=intent_result,
    )
    if t2_text is not None:
        return t2_text, "2", t2_total, t2_in, t2_out
    if not allow_tier3_fallback:
        return None, "placeholder", None, None, None
    # Backlog #40: Tier 2 fell through — capture organic candidates for
    # the renderer before the LLM call.
    organic_ctx = _organic_context_for_tier3(intent_result, db)
    text, total, tin, tout = answer_with_tier3(
        query,
        intent_result,
        db,
        onboarding_hints=onboarding_hints,
        now_line=now_line,
        organic_context=organic_ctx,
        chat_ctx=chat_ctx,
        background_tasks=background_tasks,
        telemetry=telemetry,
        component_meta=component_meta,
    )
    return text, "3", total, tin, tout


def _handle_contribute(
    query: str,
    intent_result: IntentResult,
    db: Session,
    session_id: str | None,
) -> str:
    # Stream B (2026-05-07) — deterministic intake voice. Picks WITH_URL vs
    # NO_URL variant based on whether the user's message contains a URL/domain.
    text = render_contribute_template(intent_result, query or "")
    if text is not None:
        return text
    sub = intent_result.sub_intent or "none"
    return f"Contribute mode: type={sub}. Intake flow will be implemented in Phase 4."


def _handle_correct(
    query: str,
    intent_result: IntentResult,
    db: Session,
    session_id: str | None,
) -> str:
    # Stream B (2026-05-07) — declarative acknowledge-and-log; no follow-up
    # question per handoff §8.9 (the "want to update it?" form was a judge-flagged
    # casual close).
    return render_correction_template(intent_result, query or "")


def _handle_chat(
    query: str,
    intent_result: IntentResult,
    db: Session,
    session_id: str | None,
) -> str:
    sub = intent_result.sub_intent or "SMALL_TALK"
    nq = intent_result.normalized_query

    if sub == "GREETING":
        return _greeting_variant(session_id)

    if sub == "OUT_OF_SCOPE":
        return _OUT_OF_SCOPE_REPLY

    if sub == "SMALL_TALK":
        if any(
            t in nq for t in ("thanks", "thank you", "thx", "appreciate it", "much appreciated")
        ):
            return "anytime."
        if "how are you" in nq:
            return "Pretty good, thanks."
        if any(t in nq for t in ("bye", "goodbye", "good night", "goodnight")):
            return "see you."
        return "alright."

    return _OUT_OF_SCOPE_REPLY


def _prior_entity_fresh(session: SessionState, current_turn: int) -> PriorEntity | None:
    pe = session.get("prior_entity")
    if not isinstance(pe, dict):
        return None
    t0 = pe.get("turn_number")
    if t0 is None:
        return None
    if current_turn - int(t0) <= 3:
        return pe
    return None


def _pronoun_referent_query(raw: str) -> bool:
    return bool(raw and _PRONOUN_REFERENT.search(raw))


def _enrich_entity_from_db(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    session: SessionState | None,
    current_turn: int | None,
) -> IntentResult:
    from app.chat.entity_intent import (
        is_category_open_now_listing,
        query_mentions_fake_entity_marker,
    )
    from app.chat.tier2_business_shortcut import try_business_listing_shortcut

    if query_mentions_fake_entity_marker(query or ""):
        return replace(intent_result, entity=None)
    shortcut = try_business_listing_shortcut(query or "")
    if shortcut is not None and intent_result.sub_intent not in _GAP_TIER1_FACTUAL:
        return replace(intent_result, entity=None)
    if is_category_open_now_listing(query or ""):
        return replace(intent_result, entity=None)
    if intent_result.entity is not None:
        return intent_result
    ensure_entity_matcher(db)
    hit = match_entity(query, db)
    if hit:
        name, _score = hit
        return replace(intent_result, entity=name)
    if session is not None and current_turn is not None and _pronoun_referent_query(query):
        pe = _prior_entity_fresh(session, current_turn)
        if pe and isinstance(pe.get("name"), str):
            nm = pe["name"].strip()
            if nm:
                return replace(intent_result, entity=nm)
    return intent_result


def route(
    query: str,
    session_id: str | None,
    db: Session,
    *,
    request_headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    client_ip: str | None = None,
    accept_language: str | None = None,
    preferred_mode: str | None = None,
    temperature_f_override: float | None = None,
    background_tasks: "BackgroundTasks | None" = None,
) -> ChatResponse:
    disclosure_render.reset_decision_context()
    t0 = time.perf_counter()
    sid = _stable_session_bucket(session_id)
    q_raw = query or ""
    q_hash = hashlib.sha256(q_raw.encode("utf-8")).hexdigest()

    # Lane S3: audience-signal classification — orthogonal to intent, computed
    # once per request from cheap features (CDN-provided geo headers, local
    # time, query-shape keywords). Persisted to chat_logs.audience_signal so
    # Phase 2 can decide whether to ship a visitor-mode UI. See
    # ``app/chat/audience_signal.py`` for the composition rule. Failures here
    # never block the request — we fall back to None and persist nothing.
    audience: AudienceSignal | None = None
    try:
        audience = classify_audience(
            client_ip=client_ip,
            accept_language=accept_language,
            request_time_local=now_lake_havasu(),
            query_text=q_raw,
            headers=request_headers,
        )
    except Exception:
        logging.exception("unified_router: audience signal classification failed")

    def _ms() -> int:
        return max(1, int((time.perf_counter() - t0) * 1000))

    def _finish(
        response: str,
        mode: str,
        sub: str | None,
        entity: str | None,
        tier_used: str,
        llm_tokens_used: int | None = None,
        llm_input_tokens: int | None = None,
        llm_output_tokens: int | None = None,
        voice: str | None = None,
        component_type: str = "none",
        component_data: dict | None = None,
        cache_status: str | None = None,
        timing_ms: dict | None = None,
        intent_logged: bool = False,
    ) -> ChatResponse:
        ms = _ms()
        chat_log_id: str | None = None
        try:
            chat_log_id = log_unified_route(
                db,
                session_id=sid,
                query_text_hashed=q_hash,
                normalized_query=nq_safe,
                mode=mode,
                sub_intent=sub,
                entity_matched=entity,
                tier_used=tier_used,
                latency_ms=ms,
                response_text=response,
                llm_tokens_used=llm_tokens_used,
                llm_input_tokens=llm_input_tokens,
                llm_output_tokens=llm_output_tokens,
                feedback_signal=None,
                audience_signal=audience,
                cache_status=cache_status,
                timing_ms=timing_ms,
            )
        except Exception:
            logging.exception("log_unified_route wrapper failure")
        return ChatResponse(
            response=response,
            voice=voice or response,
            component_type=component_type,
            component_data=component_data or {},
            mode=mode,
            sub_intent=sub,
            entity=entity,
            tier_used=tier_used,
            latency_ms=ms,
            llm_tokens_used=llm_tokens_used,
            llm_input_tokens=llm_input_tokens,
            llm_output_tokens=llm_output_tokens,
            chat_log_id=chat_log_id,
            intent_logged=intent_logged,
        )

    nq_safe = ""
    try:
        nq_safe = normalize(q_raw)
    except Exception:
        logging.exception("unified_router: normalize failed")
        return _finish(_GRACEFUL, "ask", None, None, "placeholder", cache_status="na")

    raw_sid = (session_id or "").strip()
    session_obj: SessionState | None = None
    current_turn: int | None = None
    if raw_sid:
        try:
            touch_session(raw_sid)
            session_obj = get_session(raw_sid)
            session_obj["turn_number"] = int(session_obj.get("turn_number", 0)) + 1
            current_turn = int(session_obj["turn_number"])
        except Exception:
            logging.exception("unified_router: session touch/increment failed")

    try:
        intent_result = classify(nq_safe)
    except Exception:
        logging.exception("unified_router: classify failed")
        return _finish(_GRACEFUL, "ask", None, None, "placeholder", cache_status="na")

    try:
        extracted = extract_hints(q_raw)
        if raw_sid:
            update_hints_from_extraction(raw_sid, extracted)
    except Exception:
        logging.exception("unified_router: hint extraction failed")

    try:
        intent_result = _enrich_entity_from_db(
            q_raw,
            intent_result,
            db,
            session=session_obj,
            current_turn=current_turn,
        )
    except Exception:
        logging.exception("unified_router: entity enrichment failed")
        # Continue with un-enriched classification

    if raw_sid and current_turn is not None and (intent_result.entity or "").strip():
        try:
            record_entity(raw_sid, intent_result.entity or "", current_turn, db)
        except Exception:
            logging.exception("unified_router: record_entity failed")

    onboarding_hints: OnboardingHints | None = None
    if raw_sid:
        try:
            raw_hints = get_session(raw_sid).get("onboarding_hints")
            if isinstance(raw_hints, dict):
                onboarding_hints = raw_hints
        except Exception:
            logging.exception("unified_router: onboarding_hints read failed")

    now_line = f"Now: {format_now_lake_havasu()}"

    chat_ctx = _build_chat_request_context(
        intent_result,
        request_headers=request_headers,
        query_params=query_params,
        preferred_mode=preferred_mode,
    )
    # Phase 8a: when no override supplied, read live temperature from cache.
    # `read_current_temperature_f` returns STUB_CURRENT_TEMPERATURE_F on
    # missing / stale data, so this is safe at cold-start. Wrap in try/except
    # so any DB/cache failure falls back to the legacy stub via the
    # ChatRequestContext default — never blocks the request.
    if temperature_f_override is None:
        try:
            temperature_f_override = read_current_temperature_f(db)
        except Exception:
            logging.exception(
                "unified_router: live conditions read failed; "
                "falling back to ChatRequestContext stub default"
            )
            temperature_f_override = None
    from app.chat.tier2_handler import detect_event_intent

    event_intent = detect_event_intent(q_raw)
    event_when = event_intent.get("when") if event_intent else None
    if temperature_f_override is not None or event_when:
        chat_ctx = ChatRequestContext(
            boat_mode=chat_ctx.boat_mode,
            # P1-15: ``is not None`` — a real 0°F reading is falsy and an ``or``
            # chain would discard it and fall back to the stub temperature.
            temperature_f=(
                temperature_f_override
                if temperature_f_override is not None
                else chat_ctx.temperature_f
            ),
            multi_domain_category_slugs=chat_ctx.multi_domain_category_slugs,
            event_intent_when=event_when or chat_ctx.event_intent_when,
        )

    tier_used = "placeholder"
    llm_tokens_used: int | None = None
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    route_telemetry: dict[str, Any] = {}
    response_mode = intent_result.mode
    response_sub_intent = intent_result.sub_intent
    response_entity = intent_result.entity
    # BUILD.md task #12: component_meta is allocated here (outside the
    # try/if-block) so all mode branches and the success-path _finish
    # call can read it. Day-shape branch in tier2_handler populates it;
    # other paths leave it empty and the response renders voice-only.
    component_meta: dict[str, object] = {}
    try:
        if intent_result.mode == "ask":
            # Gap responses return component_meta empty → component.type == "none",
            # which signals the UI to render voice-only (no skeleton flash).
            # Confirmed by tests/test_tier2_single_card.py::test_gap_path_emits_none.
            about_gap = _unknown_entity_about_gate(q_raw, intent_result, db)
            if about_gap is not None:
                route_telemetry["cache_status"] = "na"
                return _finish(
                    about_gap,
                    "ask",
                    intent_result.sub_intent,
                    intent_result.entity,
                    "gap_template",
                    None,
                    cache_status=route_telemetry.get("cache_status"),
                    timing_ms=route_telemetry or None,
                )
            gap_text = _catalog_gap_response(intent_result, db)
            router_meta: dict[str, str | None] = {}
            if gap_text is not None:
                text, tier_used, llm_tokens_used, llm_input_tokens, llm_output_tokens = _handle_ask(
                    q_raw,
                    intent_result,
                    db,
                    onboarding_hints=onboarding_hints,
                    now_line=now_line,
                    allow_tier3_fallback=False,
                    router_meta=router_meta,
                    component_meta=component_meta,
                    chat_ctx=chat_ctx,
                    background_tasks=background_tasks,
                    telemetry=route_telemetry,
                )
                if text is None:
                    route_telemetry["cache_status"] = "na"
                    return _finish(
                        gap_text,
                        "ask",
                        intent_result.sub_intent,
                        intent_result.entity,
                        "gap_template",
                        None,
                        cache_status=route_telemetry.get("cache_status"),
                        timing_ms=route_telemetry or None,
                    )
            else:
                text, tier_used, llm_tokens_used, llm_input_tokens, llm_output_tokens = _handle_ask(
                    q_raw,
                    intent_result,
                    db,
                    onboarding_hints=onboarding_hints,
                    now_line=now_line,
                    router_meta=router_meta,
                    component_meta=component_meta,
                    chat_ctx=chat_ctx,
                    background_tasks=background_tasks,
                    telemetry=route_telemetry,
                )
            if router_meta:
                response_mode = router_meta.get("mode") or response_mode
                response_sub_intent = router_meta.get("sub_intent") or response_sub_intent
                response_entity = router_meta.get("entity") or response_entity
        elif intent_result.mode == "contribute":
            route_telemetry["cache_status"] = "na"
            tier_used = "intake"
            text = _handle_contribute(q_raw, intent_result, db, session_id)
        elif intent_result.mode == "correct":
            route_telemetry["cache_status"] = "na"
            tier_used = "correction"
            text = _handle_correct(q_raw, intent_result, db, session_id)
        elif intent_result.mode == "chat":
            route_telemetry["cache_status"] = "na"
            tier_used = "chat"
            text = _handle_chat(q_raw, intent_result, db, session_id)
        else:
            text, tier_used, llm_tokens_used, llm_input_tokens, llm_output_tokens = _handle_ask(
                q_raw,
                intent_result,
                db,
                onboarding_hints=onboarding_hints,
                now_line=now_line,
                component_meta=component_meta,
                chat_ctx=chat_ctx,
                background_tasks=background_tasks,
                telemetry=route_telemetry,
            )
    except Exception:
        logging.exception("unified_router: mode handler failed")
        route_telemetry["cache_status"] = "na"
        return _finish(
            _GRACEFUL,
            intent_result.mode,
            intent_result.sub_intent,
            intent_result.entity,
            tier_used,
            llm_tokens_used=None,
            llm_input_tokens=None,
            llm_output_tokens=None,
            cache_status=route_telemetry.get("cache_status"),
            timing_ms=route_telemetry or None,
            intent_logged=bool(route_telemetry.get("intent_logged")),
        )

    # Every mode handler assigns ``text`` before we reach here (the except above
    # returns), but some are typed ``str | None``. Narrow to ``str``: a None would
    # be a bug, so fall back to the graceful message rather than passing None into
    # downstream string APIs. Byte-stable for every real (non-None) response.
    if text is None:
        text = _GRACEFUL

    if raw_sid and current_turn is not None and tier_used in ("2", "3"):
        try:
            mentioned = extract_catalog_entities_from_text(text, db)
            if len(mentioned) == 1:
                record_entity(raw_sid, mentioned[0].name, current_turn, db)
        except Exception:
            logging.exception("unified_router: recommended-entity capture failed")

    _component_type = str(component_meta.get("type") or "none")
    _component_data = component_meta.get("data") or {}
    if not isinstance(_component_data, dict):
        _component_data = {}
    return _finish(
        text,
        response_mode,
        response_sub_intent,
        response_entity,
        tier_used,
        llm_tokens_used,
        llm_input_tokens,
        llm_output_tokens,
        voice=text,
        component_type=_component_type,
        component_data=_component_data,
        cache_status=route_telemetry.get("cache_status"),
        timing_ms=route_telemetry or None,
        intent_logged=bool(route_telemetry.get("intent_logged")),
    )
