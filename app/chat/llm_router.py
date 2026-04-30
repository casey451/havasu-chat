"""LLM-backed ask-mode router (Phase 8.8.4): single structured routing decision + Tier2 filters."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.chat.tier2_schema import Tier2Filters
from app.core.llm_messages import (
    DEFAULT_MODEL,
    call_anthropic_messages,
    coerce_llm_text_to_json_object,
    load_prompt,
)

_MAX_TOKENS = 500
_TEMPERATURE = 0.0

_SUB_INTENTS = frozenset(
    {
        "TIME_LOOKUP",
        "HOURS_LOOKUP",
        "PHONE_LOOKUP",
        "LOCATION_LOOKUP",
        "WEBSITE_LOOKUP",
        "COST_LOOKUP",
        "AGE_LOOKUP",
        "DATE_LOOKUP",
        "NEXT_OCCURRENCE",
        "OPEN_NOW",
        "LIST_BY_CATEGORY",
        "OPEN_ENDED",
        "NEW_EVENT",
        "NEW_PROGRAM",
        "NEW_BUSINESS",
        "CORRECTION",
        "GREETING",
        "SMALL_TALK",
        "OUT_OF_SCOPE",
    }
)


def _load_router_system_prompt() -> str:
    """Delegate to :func:`load_prompt` — kept for ``tests/test_llm_router.py`` imports."""
    return load_prompt("llm_router")


class RouterDecision(BaseModel):
    """Structured router output used when ``USE_LLM_ROUTER`` is on."""

    mode: str
    sub_intent: str
    entity: Optional[str] = None
    router_confidence: float = Field(..., ge=0.0, le=1.0)
    tier_recommendation: str
    tier2_filters: Optional[Tier2Filters] = None

    @field_validator("mode")
    @classmethod
    def _mode_ok(cls, v: object) -> str:
        s = str(v).lower().strip() if v is not None else ""
        if s not in ("ask", "contribute", "correct", "chat"):
            raise ValueError("mode must be ask, contribute, correct, or chat")
        return s

    @field_validator("sub_intent")
    @classmethod
    def _sub_ok(cls, v: object) -> str:
        s = str(v).upper().replace(" ", "_").strip() if v is not None else ""
        if s not in _SUB_INTENTS:
            raise ValueError("sub_intent must be a known sub-intent label (see spec)")
        return s

    @field_validator("entity", mode="before")
    @classmethod
    def _empty_entity_none(cls, v: object) -> str | None:
        if v is None:
            return None
        t = str(v).strip()
        if not t or t.lower() in ("null", "none", ""):
            return None
        return t

    @field_validator("tier_recommendation")
    @classmethod
    def _tier_rec(cls, v: object) -> str:
        s = str(v).strip() if v is not None else ""
        if s not in ("2", "3"):
            raise ValueError('tier_recommendation must be "2" or "3"')
        return s

    @model_validator(mode="after")
    def _tier2_if_recommended(self) -> RouterDecision:
        if self.tier_recommendation == "2" and self.tier2_filters is None:
            raise ValueError('When tier_recommendation is "2", tier2_filters is required')
        return self


def route(
    query: str,
    normalized_query: str,
    context: Optional[dict] = None,
) -> Optional[RouterDecision]:
    """
    One Anthropic call returning a single JSON object, validated to :class:`RouterDecision`.

    On any failure, returns ``None`` (caller falls back to Tier3 for ask mode).
    """
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        logging.info("llm_router: ANTHROPIC_API_KEY unset; skipping router")
        return None

    try:
        system_prompt = _load_router_system_prompt()
    except OSError as e:
        logging.error("llm_router: %s", e)
        return None

    uq = (normalized_query or query or "").strip()
    rq = (query or "").strip()
    extra = ""
    if context:
        try:
            extra = "\nSession context (JSON)\n" + json.dumps(context, default=str) + "\n"
        except TypeError:
            extra = f"\nSession context (unserializable): {context!r}\n"

    user_text = f"raw_query:\n{rq}\n\nnormalized_query:\n{uq}\n{extra}\n"

    model = (os.getenv("ANTHROPIC_MODEL") or "").strip() or DEFAULT_MODEL
    t0 = time.perf_counter()
    result = call_anthropic_messages(
        system_prompt=system_prompt,
        user_text=user_text,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        model=None,
    )
    ms = (time.perf_counter() - t0) * 1000.0

    if result is None:
        logging.error("llm_router: Anthropic messages.create failed")
        return None

    if getattr(result.raw, "usage", None) is None:
        in_t, out_t = None, None
    else:
        in_t = result.usage.billable_input
        out_t = result.usage.output_tokens

    data = coerce_llm_text_to_json_object(result.text)
    if not data:
        logging.warning("llm_router: response is not valid JSON object; latency_ms=%.1f", ms)
        return None
    try:
        d = dict(data)
        tf = d.get("tier2_filters")
        if tf is not None and isinstance(tf, dict) and len(tf) > 0:
            d["tier2_filters"] = Tier2Filters.model_validate(tf)
        else:
            d["tier2_filters"] = None
        decision = RouterDecision.model_validate(d)
    except Exception:
        logging.exception("llm_router: JSON does not validate; latency_ms=%.1f", ms)
        return None

    log_msg = f"llm_router: ok model={model} latency_ms={ms:.1f}"
    if in_t is not None and out_t is not None:
        log_msg += f" in_tokens~={in_t} out_tokens~={out_t} tier={decision.tier_recommendation}"
    else:
        log_msg += f" tier={decision.tier_recommendation}"
    logging.info(log_msg)
    return decision
