"""OpenAI hint extraction for session memory (Phase 6.4).

Separate from heuristic ``classify()`` — one gpt-4.1-mini JSON call per turn when
``OPENAI_API_KEY`` is set. On failure or missing key, returns ``None`` (no-op).

Signal gate (2026-06-04): the prompt only ever extracts an explicit child age
("my 6-year-old", "for a teenager") or a specific Lake Havasu location ("near
the island", "staying downtown"), so a message containing none of those signals
cannot produce a hint. We pre-screen with a cheap regex and skip the API call
when no signal is present. At ~$0.0003 and ~1s per call on every chat turn,
this call site was the dominant per-turn cost and latency line at scale.
Kill switch: set ``HINT_GATE`` to ``0``/``false``/``no``/``off`` to restore the
old call-every-turn behavior.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.chat.intents.dicts import AREA_DICT
from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[misc, assignment]

# Soft-budget for prompt-tuning observability. Bumped from 300/100 to 400/100
# after Phase 7.5 close-out empirically observed inp=~378 per call. Real prompt
# at prompts/hint_extractor.txt is ~370 tokens; the system intends 100-token
# response headroom. Bumping inp avoids 22× warning noise per HALT 3 run
# while preserving the warning's purpose (catching unexpected ballooning).
_SOFT_BUDGET_INP = 400
_SOFT_BUDGET_OUT = 100

# --- Signal gate -----------------------------------------------------------
# Age: digits ("my 6 year old", "for 9-12 year olds") or age words. "kid" /
# "adult" alone are NOT signals — the prompt explicitly refuses to infer age
# from them, so gating them out loses nothing.
_AGE_SIGNALS = r"\d|year|yr\b|teen|toddler|month[- ]old"
# Location: relational phrases that introduce a place, plus the canonical Lake
# Havasu area names (kept in sync with the intent layer via AREA_DICT), plus
# common landmark words from prompts/hint_extractor.txt examples.
_LOCATION_PHRASES = [
    "near",
    "close to",
    "staying",
    "by the",
    "next to",
    "walking distance",
    "channel",
    "london bridge",
]
_SIGNAL_RE = re.compile(
    "|".join(
        [_AGE_SIGNALS]
        + [re.escape(p) for p in _LOCATION_PHRASES]
        + [re.escape(k) for k in AREA_DICT]
    ),
    re.IGNORECASE,
)


def _gate_enabled() -> bool:
    return (os.getenv("HINT_GATE") or "").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def has_hint_signal(query: str) -> bool:
    """True when the message plausibly contains an age or location hint."""
    return bool(_SIGNAL_RE.search(query or ""))


class ExtractedHints(BaseModel):
    age: int | str | None = None
    location: str | None = None


class _HintEnvelope(BaseModel):
    extracted_hints: ExtractedHints | None = None


def _load_hint_prompt() -> str:
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / "hint_extractor.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return (
        'Return JSON: {"extracted_hints": null} unless age or location is explicitly given '
        "per Lake Havasu local phrasing rules."
    )


def extract_hints(query: str) -> ExtractedHints | None:
    """Call gpt-4.1-mini for optional age/location hints. Returns ``None`` on skip/failure."""
    q = (query or "").strip()
    if not q:
        return None
    if _gate_enabled() and not has_hint_signal(q):
        return None
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or OpenAI is None:
        return None

    model = (os.getenv("OPENAI_MODEL") or "").strip() or "gpt-4.1-mini"
    system = _load_hint_prompt()
    user = f"User message:\n{q}"

    try:
        client = OpenAI(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    except Exception:
        logging.exception("hint_extractor: OpenAI chat.completions.create failed")
        return None

    choice = completion.choices[0] if completion.choices else None
    raw = (choice.message.content or "").strip() if choice and choice.message else ""
    if not raw:
        return None

    usage = getattr(completion, "usage", None)
    if usage is not None:
        inp = int(getattr(usage, "prompt_tokens", 0) or 0)
        out = int(getattr(usage, "completion_tokens", 0) or 0)
        if inp > _SOFT_BUDGET_INP or out > _SOFT_BUDGET_OUT:
            logging.warning(
                "hint_extractor: token usage exceeds soft budget (inp=%s out=%s)",
                inp,
                out,
            )

    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        logging.info("hint_extractor: invalid JSON from model")
        return None

    try:
        env = _HintEnvelope.model_validate(data)
    except Exception:
        logging.info(
            "hint_extractor: envelope validation failed (raw length=%d)",
            len(raw or ""),
        )
        return None

    if env.extracted_hints is None:
        return None
    h = env.extracted_hints
    loc_ok = isinstance(h.location, str) and h.location.strip()
    if h.age is None and not loc_ok:
        return None
    return h
