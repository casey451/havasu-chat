"""LLM-backed ask-mode router (Phase 8.8.4): single structured routing decision + Tier2 filters."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import anthropic
from pydantic import BaseModel, Field, field_validator, model_validator

from app.chat.tier2_schema import Tier2Filters
from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
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
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / "llm_router.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"llm router prompt missing: {path}")


def _extract_text_from_message(msg: object) -> str:
    parts: list[str] = []
    for block in getattr(msg, "content", None) or []:
        if getattr(block, "type", None) == "text":
            t = getattr(block, "text", "") or ""
            if t:
                parts.append(t)
    return " ".join(parts).strip()


def _coerce_llm_text_to_json_object(raw: str) -> Optional[dict[str, Any]]:
    s = raw.strip()
    if not s:
        return None
    if s.startswith("```"):
        first = s.find("\n")
        if first == -1:
            return None
        inner = s[first + 1 :]
        fence = inner.rfind("```")
        if fence != -1:
            inner = inner[:fence]
        s = inner.strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _usage_in_out(msg: object) -> tuple[int | None, int | None]:
    u = getattr(msg, "usage", None)
    if u is None:
        return None, None
    inp = int(getattr(u, "input_tokens", 0) or 0) + int(getattr(u, "cache_read_input_tokens", 0) or 0) + int(
        getattr(u, "cache_creation_input_tokens", 0) or 0
    )
    return inp, int(getattr(u, "output_tokens", 0) or 0)


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

    model = (os.getenv("ANTHROPIC_MODEL") or "").strip() or _DEFAULT_MODEL
    t0 = time.perf_counter()
    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
        msg = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
        )
    except Exception:
        logging.exception("llm_router: Anthropic messages.create failed")
        return None
    ms = (time.perf_counter() - t0) * 1000.0
    in_t, out_t = _usage_in_out(msg)
    text = _extract_text_from_message(msg)
    data = _coerce_llm_text_to_json_object(text)
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
