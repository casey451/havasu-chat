"""Unified concierge router (Phase 2.2 — handoff §3.2, §5 Phase 2.2).

Orchestrates normalize → classify → entity enrichment → mode handler → log.
Ask uses Tier 1 when applicable, else Tier 3 (Anthropic); contribute / correct use placeholder copy;
chat uses real short responses (§8).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, replace
from uuid import uuid4

from sqlalchemy.orm import Session

from app.chat.entity_matcher import match_entity, refresh_entity_matcher
from app.chat.intent_classifier import IntentResult, classify
from app.chat.normalizer import normalize
from app.chat.tier1_handler import try_tier1
from app.chat.tier2_handler import try_tier2_with_usage
from app.chat.tier3_handler import answer_with_tier3
from app.db.chat_logging import log_unified_route

_GRACEFUL = "Something went sideways on my end — try that again in a sec."

_GREETINGS: tuple[str, ...] = (
    "Heya.",
    "Hey.",
    "Hey, good to see you.",
)

_OUT_OF_SCOPE_REPLY = (
    "That's outside what I cover right now — I stick to things-to-do, local businesses, and events. "
    "Want me to point you to anything else?"
)


_GAP_TAIL = (
    "Add it at /contribute or share the name and a link (Google Business page or official site) — either works."
)


def _catalog_gap_response(intent_result: IntentResult) -> str | None:
    """Tier 1-shaped fact lookup with no catalog entity — template only, no Tier 3."""
    sub = intent_result.sub_intent
    if sub not in ("DATE_LOOKUP", "LOCATION_LOOKUP", "HOURS_LOOKUP"):
        return None
    if (intent_result.entity or "").strip():
        return None
    if sub == "HOURS_LOOKUP":
        return f"I don't have those business hours in the catalog yet. {_GAP_TAIL}"
    if sub == "LOCATION_LOOKUP":
        return f"I don't have that place in the catalog yet. {_GAP_TAIL}"
    return f"I don't have that event or program in the catalog yet. {_GAP_TAIL}"


@dataclass
class ChatResponse:
    response: str
    mode: str
    sub_intent: str | None
    entity: str | None
    tier_used: str  # '1' | '2' | '3' | 'gap_template' | 'intake' | 'correction' | 'chat' | 'placeholder'
    latency_ms: int
    llm_tokens_used: int | None = None
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    chat_log_id: str | None = None


def _stable_session_bucket(session_id: str | None) -> str:
    if session_id and session_id.strip():
        return session_id.strip()[:128]
    return uuid4().hex[:24]


def _greeting_variant(session_id: str | None) -> str:
    key = (session_id or "__anon__").encode("utf-8")
    idx = int(hashlib.sha256(key).hexdigest(), 16) % len(_GREETINGS)
    return _GREETINGS[idx]


def _handle_ask(
    query: str, intent_result: IntentResult, db: Session
) -> tuple[str, str, int | None, int | None, int | None]:
    tier1 = try_tier1(query, intent_result, db)
    if tier1 is not None:
        return tier1, "1", None, None, None
    t2_text, t2_total, t2_in, t2_out = try_tier2_with_usage(query)
    if t2_text is not None:
        return t2_text, "2", t2_total, t2_in, t2_out
    text, total, tin, tout = answer_with_tier3(query, intent_result, db)
    return text, "3", total, tin, tout


def _handle_contribute(
    query: str,
    intent_result: IntentResult,
    db: Session,
    session_id: str | None,
) -> str:
    sub = intent_result.sub_intent or "none"
    return f"Contribute mode: type={sub}. Intake flow will be implemented in Phase 4."


def _handle_correct(
    query: str,
    intent_result: IntentResult,
    db: Session,
    session_id: str | None,
) -> str:
    return "Correct mode: received. Correction flow will be implemented in Phase 5."


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
        if any(t in nq for t in ("thanks", "thank you", "thx", "appreciate it", "much appreciated")):
            return "anytime."
        if "how are you" in nq:
            return "doing alright. what can I find for you?"
        if any(t in nq for t in ("bye", "goodbye", "good night", "goodnight")):
            return "see you."
        return "alright."

    return _OUT_OF_SCOPE_REPLY


def _enrich_entity_from_db(query: str, intent_result: IntentResult, db: Session) -> IntentResult:
    if intent_result.entity is not None:
        return intent_result
    refresh_entity_matcher(db)
    hit = match_entity(query, db)
    if not hit:
        return intent_result
    name, _score = hit
    return replace(intent_result, entity=name)


def route(query: str, session_id: str | None, db: Session) -> ChatResponse:
    t0 = time.perf_counter()
    sid = _stable_session_bucket(session_id)
    q_raw = query or ""
    q_hash = hashlib.sha256(q_raw.encode("utf-8")).hexdigest()

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
            )
        except Exception:
            logging.exception("log_unified_route wrapper failure")
        return ChatResponse(
            response=response,
            mode=mode,
            sub_intent=sub,
            entity=entity,
            tier_used=tier_used,
            latency_ms=ms,
            llm_tokens_used=llm_tokens_used,
            llm_input_tokens=llm_input_tokens,
            llm_output_tokens=llm_output_tokens,
            chat_log_id=chat_log_id,
        )

    nq_safe = ""
    try:
        nq_safe = normalize(q_raw)
    except Exception:
        logging.exception("unified_router: normalize failed")
        return _finish(_GRACEFUL, "ask", None, None, "placeholder")

    try:
        intent_result = classify(nq_safe)
    except Exception:
        logging.exception("unified_router: classify failed")
        return _finish(_GRACEFUL, "ask", None, None, "placeholder")

    try:
        intent_result = _enrich_entity_from_db(q_raw, intent_result, db)
    except Exception:
        logging.exception("unified_router: entity enrichment failed")
        # Continue with un-enriched classification

    if intent_result.mode == "ask":
        gap_text = _catalog_gap_response(intent_result)
        if gap_text is not None:
            return _finish(
                gap_text,
                "ask",
                intent_result.sub_intent,
                intent_result.entity,
                "gap_template",
                None,
            )

    tier_used = "placeholder"
    llm_tokens_used: int | None = None
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    try:
        if intent_result.mode == "ask":
            text, tier_used, llm_tokens_used, llm_input_tokens, llm_output_tokens = _handle_ask(
                q_raw, intent_result, db
            )
        elif intent_result.mode == "contribute":
            tier_used = "placeholder"
            text = _handle_contribute(q_raw, intent_result, db, session_id)
        elif intent_result.mode == "correct":
            tier_used = "placeholder"
            text = _handle_correct(q_raw, intent_result, db, session_id)
        elif intent_result.mode == "chat":
            tier_used = "chat"
            text = _handle_chat(q_raw, intent_result, db, session_id)
        else:
            text, tier_used, llm_tokens_used, llm_input_tokens, llm_output_tokens = _handle_ask(
                q_raw, intent_result, db
            )
    except Exception:
        logging.exception("unified_router: mode handler failed")
        return _finish(
            _GRACEFUL,
            intent_result.mode,
            intent_result.sub_intent,
            intent_result.entity,
            tier_used,
            llm_tokens_used=None,
            llm_input_tokens=None,
            llm_output_tokens=None,
        )

    return _finish(
        text,
        intent_result.mode,
        intent_result.sub_intent,
        intent_result.entity,
        tier_used,
        llm_tokens_used,
        llm_input_tokens,
        llm_output_tokens,
    )
