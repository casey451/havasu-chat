"""Tier 2 response formatting from catalog rows (Phase 4.2). Import-only until routing."""

from __future__ import annotations

import json
import logging
import os
import re
from types import SimpleNamespace

from app.chat import tier2_catalog_render
from app.chat.confidence_tier import (
    ConfidenceTier,
    classify_confidence,
    hedge_phrase,
)
from app.core.llm_messages import call_anthropic_messages, load_prompt
from app.core.timezone import now_lake_havasu

_MAX_OUTPUT_TOKENS = 400
_TEMPERATURE = 0.3

EMPTY_CATALOG_MESSAGE = "No matching catalog rows."

# feature flag (Lane CT2.A)
FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR = "FEATURE_FLAG_CONFIDENCE_TIER"


def is_confidence_tier_enabled() -> bool:
    """Return True only when FEATURE_FLAG_CONFIDENCE_TIER=true (case-insensitive).

    Mirrors app.chat.disclosure_render.is_renderer_enabled so the
    integration ships behind a flag with byte-identical default-off
    behavior. When unset, format() skips classification and the row
    dicts the LLM sees are unchanged from the pre-CT2 path.
    """
    return (
        os.environ.get(FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "")
        .strip()
        .lower()
        == "true"
    )


_LEGACY_FALLBACK_RE = re.compile(
    r"\bImported from River Scene\. Event URL:\s*\S+\s*",
    re.IGNORECASE,
)


def _strip_legacy_fallback(description):
    if not description:
        return description or ""
    return _LEGACY_FALLBACK_RE.sub("", description, count=1).strip()


def _inject_event_url_links(text, rows):
    out = text
    for row in rows:
        if row.get("type") != "event":
            continue
        url = str(row.get("event_url") or "").strip()
        name = str(row.get("name") or "").strip()
        if not url or not name:
            continue
        link = f"[{name}]({url})"
        if link in out:
            continue
        pattern = r"\b" + re.escape(name) + r"\b"
        injected = False
        for m in re.finditer(pattern, out):
            before = out[: m.start()]
            last_open = before.rfind("[")
            last_close = before.rfind("]")
            if last_open > last_close:
                continue
            insert_at = m.end()
            out = out[:insert_at] + f" {link}" + out[insert_at:]
            injected = True
            break
        if not injected:
            out = out.rstrip() + f"\n\n{link}"
    return out


_VERIFICATION_FIELDS = {"last_verified_at", "verification_method"}

# Backlog #48 — skip LOW-tier phone append when the LLM voice already stated no hit.
_LLM_NEGATION_VOICE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bno results?\b", re.IGNORECASE),
    re.compile(r"\bnot in (?:the\s+)?catalog\b", re.IGNORECASE),
    re.compile(r"\bi\s+don'?t\s+have\b", re.IGNORECASE),
    re.compile(r"\bi\s+don'?t\s+see\b", re.IGNORECASE),
    re.compile(r"\bno\s+\w+\s+listed\b", re.IGNORECASE),
)


def _llm_voice_denies_catalog_hit(text: str) -> bool:
    """True when the assistant already told the user nothing matched."""
    low = (text or "").lower()
    return any(p.search(low) for p in _LLM_NEGATION_VOICE_PATTERNS)


def _annotate_rows_with_confidence_hint(rows):
    """Attach confidence_hint + confidence_hedge per row (Lane CT2.A).

    Classifier is called once per row with an explicit ``now`` so all
    rows in a single response share the same clock read (no skew across
    the loop). The classifier reads ``last_verified_at`` and
    ``verification_method`` defensively via ``getattr``; row dicts that
    don't carry those keys classify LOW with rationale
    "no verification record" -- accepted per the spec's section 10
    decision (legacy rows opt out via Lane S1's schema rollout, not via
    a sentinel).

    Verification fields are stripped from the row dict that reaches the
    LLM serializer because (a) they are not row-backed facts the LLM
    should surface, and (b) ``last_verified_at`` is typically a
    datetime which would crash ``json.dumps`` downstream. The
    confidence-tier annotation captures everything the LLM needs.
    """
    now = now_lake_havasu()
    annotated = []
    for r in rows:
        record = SimpleNamespace(**r)
        try:
            assessment = classify_confidence(record, now=now)
            tier_value = assessment.tier.value
            hedge = hedge_phrase(assessment.tier)
        except Exception:
            logging.exception(
                "tier2_formatter: classify_confidence raised on row, defaulting to no hint"
            )
            tier_value = ""
            hedge = ""
        clean = {k: v for k, v in r.items() if k not in _VERIFICATION_FIELDS}
        clean["confidence_hint"] = tier_value
        clean["confidence_hedge"] = hedge
        annotated.append(clean)
    return annotated


def _enforce_low_tier_phone(text, rows):
    """Append a phone-number hedge when a LOW row's phone is absent (Lane CT2.A).

    Backstop for the prompt-side ask in prompts/tier2_formatter.txt that
    instructs the LLM to inline a phone alongside the LOW hedge. Mirrors
    _inject_event_url_links -- pure post-process, no LLM calls,
    deterministic for fixed inputs.

    Per row, when:
    - confidence_hint == "low" (annotated by
      _annotate_rows_with_confidence_hint), AND
    - the row carries a non-empty phone, AND
    - the response text does NOT already contain that phone, AND
    - the response text does NOT already carry an equivalent hedge
      ("recommend calling" / "call to confirm")

    append "Their listed number is {phone} -- recommend calling to
    confirm." on its own line. The "already hedged" check prevents
    double-hedging when the LLM correctly inlined the canonical fragment
    but happened to omit the phone.
    """
    if not text:
        return text
    if _llm_voice_denies_catalog_hit(text):
        return text
    out = text
    for row in rows:
        if (row.get("confidence_hint") or "").lower() != ConfidenceTier.LOW.value:
            continue
        phone = str(row.get("phone") or "").strip()
        if not phone:
            continue
        if phone in out:
            continue
        lowered = out.lower()
        if "recommend calling" in lowered or "call to confirm" in lowered:
            continue
        out = out.rstrip() + f"\n\nTheir listed number is {phone} -- recommend calling to confirm."
    return out


def postprocess(text, rows):
    """Apply deterministic post-processors to a formatter response (Backlog #49 parity).

    Tier 2 cache stores the raw LLM output (no URL injection, no LOW-tier
    phone hedge). On both cache miss and cache hit, callers run this
    helper so flag flips on ``is_confidence_tier_enabled()`` and edits to
    ``_inject_event_url_links`` / ``_enforce_low_tier_phone`` take effect
    immediately instead of waiting for the 1-day TTL to expire. Mirrors
    the Tier 3 pattern in ``app/chat/tier3_handler.py`` (see comments at
    line 332-334 referencing Backlog #49).

    Safe to call on ``None`` / empty text: returns the input unchanged so
    cache-miss callers don't need to special-case a failed LLM call.
    """
    if not text:
        return text
    out = _inject_event_url_links(text, rows)
    if is_confidence_tier_enabled():
        out = _enforce_low_tier_phone(out, rows)
    return out


def _format_via_llm(query, rows):
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logging.info("tier2_formatter: OPENAI_API_KEY unset")
        return None, None, None

    try:
        system_prompt = load_prompt("tier2_formatter")
    except OSError:
        logging.exception("tier2_formatter: failed to read formatter system prompt")
        return None, None, None

    rows_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    user_text = (
        f"Query: {query.strip()}\n\n"
        f"Catalog rows:\n{rows_json}\n\n"
        "Respond:"
    )

    result = call_anthropic_messages(
        system_prompt=system_prompt,
        user_text=user_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_TEMPERATURE,
        model=None,
    )
    if result is None:
        logging.error("tier2_formatter: OpenAI chat.completions.create failed")
        return None, None, None

    if not result.text:
        logging.warning("tier2_formatter: empty model response")
        return None, result.usage.billable_input, result.usage.output_tokens

    in_tok = result.usage.billable_input
    out_tok = result.usage.output_tokens
    if getattr(result.raw, "usage", None) is not None:
        logging.info("tier2_formatter: tokens in=%s out=%s", in_tok, out_tok)
    return result.text, in_tok, out_tok


def format(query, rows):
    """Render DB rows into a response. Returns (raw_text, input_tokens, output_tokens).

    Empty rows and all-event rows use deterministic paths (0 formatter tokens).

    Backlog #49: ``raw_text`` is the **unprocessed** LLM output -- it has
    NOT had ``_inject_event_url_links`` or ``_enforce_low_tier_phone``
    applied. Callers MUST run :func:`postprocess` on the result before
    returning it to the user (and again on any cache-hit string), so flag
    flips take effect without waiting for the cached entry to expire.
    """
    rows = [
        {**r, "description": _strip_legacy_fallback(r.get("description"))}
        if "description" in r
        else r
        for r in rows
    ]

    # Lane CT2.A -- per-row confidence-tier annotation behind feature flag.
    if is_confidence_tier_enabled():
        rows = _annotate_rows_with_confidence_hint(rows)

    if not rows:
        return EMPTY_CATALOG_MESSAGE, 0, 0

    if all(r.get("type") == "event" for r in rows):
        try:
            text = tier2_catalog_render.render_tier2_events(query, rows)
            if not (text or "").strip():
                logging.warning("tier2_formatter: deterministic render returned empty")
                return None, None, None
            return text.strip(), 0, 0
        except Exception:
            logging.exception("tier2_formatter: deterministic render failed")
            return None, None, None

    text, in_tok, out_tok = _format_via_llm(query, rows)
    return text, in_tok, out_tok
