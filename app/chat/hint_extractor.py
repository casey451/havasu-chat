"""OpenAI hint extraction for session memory (Phase 6.4).

Separate from heuristic ``classify()`` — one gpt-4.1-mini JSON call per turn when
``OPENAI_API_KEY`` is set. On failure or missing key, returns ``None`` (no-op).
The extracted age/location feed *session onboarding hints* (Tier-3 user-context
line + priors selection); they do **not** change tier routing.

Signal gate (2026-06-04): the prompt only ever extracts an explicit child age
("my 6-year-old", "for a teenager") or a specific Lake Havasu location ("near
the island", "staying downtown"), so a message containing none of those signals
cannot produce a hint. We pre-screen with a cheap regex and skip the API call
when no signal is present. At ~$0.0003 and ~1s per call on every chat turn,
this call site was the dominant per-turn cost and latency line at scale.

Mode (``HINT_EXTRACTOR_MODE``, default ``conditional`` — VPS rollout HANDOFF #1):
- ``conditional`` — call the LLM only when the cheap regex finds a plausible
  age/location signal (the shipped default; ~86% of turns skip the call).
- ``always`` — call on every turn (the pre-gate behavior).
- ``off`` — never call (extraction fully disabled; exact-key paths elsewhere
  are unaffected).
Back-compat: the legacy ``HINT_GATE`` env still works — ``HINT_GATE=off`` maps to
``always``, anything else maps to ``conditional``. ``HINT_EXTRACTOR_MODE`` wins
when both are set.

Near-me exclusion (HANDOFF #1): measurement found 25% of gate-passing turns were
"... near me" / "nearby", which the prompt can never turn into a location hint
("me" is not a place). Those are excluded from the location signal so they no
longer pay for a guaranteed-null LLM call.

Telemetry: ``get_hint_extractor_telemetry()`` returns per-outcome counts
(skipped_prefilter / called / memoized / ...) so the call mix can be measured on
real traffic — which is what should gate any future session-memoization work.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.chat.intents.dicts import AREA_DICT
from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.openai_client import get_openai_client

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
# Age: a digit ADJACENT to an age unit ("my 6 year old", "8yo", "for 9-12 year
# olds", "3 month old") or an age-stage word. A *bare* digit is NOT a signal —
# the prompt explicitly refuses to infer age from a number alone, so "open at
# 5?" / "table for 4" no longer pay the ~1s LLM call for nothing. "kid"/"adult"
# alone are likewise non-signals. (P1-2)
_AGE_SIGNALS = (
    r"\b\d{1,2}\s*[-–]?\s*(?:years?|yrs?|y/?o|months?)\b"
    r"|\byears?\s+old\b|\bteen|\btoddler|month[- ]old"
)
# Location: relational phrases that introduce a place, plus the canonical Lake
# Havasu area names (kept in sync with the intent layer via AREA_DICT), plus
# common landmark words from prompts/hint_extractor.txt examples.
#
# "near" is handled specially: it must introduce a real place ("near the
# island") but NOT the empty deictic "near me" / "near here" / "near by". The
# one-word "nearby" already fails the \bnear\b boundary, so the lookahead only
# needs to drop the two-word forms. (HANDOFF #1 — 25% of gate passers were these.)
_NEAR_SIGNAL = r"\bnear\b(?!\s+(?:me|here|by)\b)"
_LOCATION_PHRASES = [
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
        [_AGE_SIGNALS, _NEAR_SIGNAL]
        + [re.escape(p) for p in _LOCATION_PHRASES]
        + [re.escape(k) for k in AREA_DICT]
    ),
    re.IGNORECASE,
)

# --- Mode resolution -------------------------------------------------------
_VALID_MODES = {"always", "conditional", "off"}


def _resolve_mode() -> str:
    """Return ``always`` | ``conditional`` | ``off`` (default ``conditional``).

    ``HINT_EXTRACTOR_MODE`` takes precedence; an unrecognized value falls back to
    the default. Otherwise the legacy ``HINT_GATE`` env is honored for
    back-compat (``off`` -> ``always``, anything else -> ``conditional``).
    """
    raw_mode = (os.getenv("HINT_EXTRACTOR_MODE") or "").strip().lower()
    if raw_mode in _VALID_MODES:
        return raw_mode
    legacy = (os.getenv("HINT_GATE") or "").strip().lower()
    if legacy in {"0", "false", "no", "off"}:
        return "always"
    return "conditional"


# --- Telemetry -------------------------------------------------------------
# Per-outcome call mix so the prefilter's effect (and any future memoization)
# can be measured on real traffic. ``memoized`` is reserved for the deferred
# session-memoization work and stays 0 until that lands.
_OUTCOMES = (
    "skipped_empty",
    "skipped_mode_off",
    "skipped_prefilter",
    "skipped_no_key",
    "memoized",
    "called",
)
_TELEMETRY: Counter[str] = Counter()


def _record(outcome: str) -> None:
    _TELEMETRY[outcome] += 1
    logging.debug("hint_extractor outcome=%s", outcome)


def get_hint_extractor_telemetry() -> dict[str, int]:
    """Snapshot of per-outcome call counts since process start (or last reset)."""
    return {k: _TELEMETRY.get(k, 0) for k in _OUTCOMES}


def reset_hint_extractor_telemetry() -> None:
    """Zero the counters (used by tests; safe to call at any time)."""
    _TELEMETRY.clear()


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
        _record("skipped_empty")
        return None
    mode = _resolve_mode()
    if mode == "off":
        _record("skipped_mode_off")
        return None
    if mode == "conditional" and not has_hint_signal(q):
        _record("skipped_prefilter")
        return None
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or OpenAI is None:
        _record("skipped_no_key")
        return None
    _record("called")

    model = (os.getenv("OPENAI_MODEL") or "").strip() or "gpt-4.1-mini"
    system = _load_hint_prompt()
    user = f"User message:\n{q}"

    try:
        client = get_openai_client(  # T2.3 singleton; OpenAI stays the patchable seam
            api_key, factory=OpenAI, timeout=LLM_CLIENT_READ_TIMEOUT_SEC
        )
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
