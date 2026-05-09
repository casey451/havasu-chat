"""Deterministic sponsored-disclosure renderer (Phase 1 keystone, Lane X1).

Spec: ``docs/maintainability/disclosure_renderer_spec.md``.

The renderer turns an eligible ``Sponsor`` row into a fully-formed
``SponsoredBlock`` without ever asking an LLM to phrase the disclosure
word, the attribution, or the body. Failure modes that motivated this
module:

1. **Disclosure-word drift.** LLM-rendered disclosures wandered between
   "Featured", "Partner", "Recommended", "Spotlight". The canonical FTC
   word is ``"Sponsored"``; this module owns the constant and refuses to
   emit anything else.
2. **Tone violations.** LLM-synthesized advertiser copy reached for
   superlatives ("best in town", "highly rated") that aren't grounded in
   verified data. The tone allowlist (``DISALLOWED_PHRASES``) rejects any
   block whose body or attribution contains marketing voice.

The renderer is pure: given the same inputs (regime + candidate sponsors
+ context) it always returns the same struct. No randomness, no
LLM calls, no clock reads outside what the caller supplies.

This module ships behind a feature flag (``FEATURE_FLAG_DISCLOSURE_RENDERER``).
Phase 1 lands the module + tests only; Tier 3 integration is Lane X2 and
is invoked only when the flag is true. See spec §7 for the migration path.
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.models import Sponsor, SponsorStatus

# ─────────── public constants ───────────

DISCLOSURE_WORD = "Sponsored"
"""Canonical FTC disclosure word. Never "Featured" / "Partner" / etc.

Imported by spotlight builders and Tier 3 integration so a single string
literal change here propagates everywhere — see spec §4.
"""

FEATURE_FLAG_ENV_VAR = "FEATURE_FLAG_DISCLOSURE_RENDERER"


class PlacementRegime(str, Enum):
    """Placement eligibility regime derived from query intent (spec §1)."""

    SPECIFIC_QUALITY = "specific_quality"  # entity + factual lookup → no sponsored
    GENERIC_CATEGORY = "generic_category"  # category-shaped ask → sponsored eligible
    EMERGENCY_URGENT = "emergency_urgent"  # time-sensitive → strict reliability bar


@dataclass(frozen=True)
class SponsoredBlock:
    """Rendered sponsored content for injection into a chat response.

    Frozen so callers can safely cache and pass around without worrying
    about mutation. ``sponsor_id`` is carried for impression/click logging
    at the API boundary.
    """

    disclosure_word: str
    body: str
    cta: Optional[str]
    attribution: str
    sponsor_id: str
    regime: PlacementRegime


@dataclass(frozen=True)
class RenderDecision:
    """Lane P2.OBS.1 telemetry — what the renderer decided this turn.

    Recorded for every renderer invocation regardless of whether a
    SponsoredBlock was produced, so Phase 2 can audit hedge-leakage on
    HIGH-confidence rows, measure regime-selection accuracy against the
    audience-signal data (Backlog #39), and gate Premier inventory open
    on real telemetry. Persisted to ``chat_logs`` via four typed columns
    added in Alembic revision ``e7f8a9b0c1d2``.

    Field semantics:

    * ``regime`` — always set; the regime selected from the turn's intent.
    * ``eligible`` — None when no candidates were evaluated (regime
      ``SPECIFIC_QUALITY`` or zero candidates fetched), False when
      candidates existed but all failed the per-regime eligibility gate
      (status / verified_fields / organic-pairing / temporal), True when
      at least one candidate passed.
    * ``sponsor_id`` — the picked sponsor's ``id`` when the deterministic
      tie-break selected one (regardless of downstream tone outcome, so
      Phase 2 can debug "which sponsor's verified data was incomplete").
      None when nothing was picked.
    * ``tone_allowlist_passed`` — None when the tone check was never
      reached (no sponsor picked), True/False from the actual check.
    """

    regime: PlacementRegime
    eligible: Optional[bool] = None
    sponsor_id: Optional[str] = None
    tone_allowlist_passed: Optional[bool] = None


# ─────────── tone allowlist ───────────

DISALLOWED_PHRASES: tuple[str, ...] = (
    # Superlatives
    r"\b(?:best|top|leading|premier|finest|outstanding)\b",
    r"\b(?:highest[-\s]rated|best[-\s]reviewed|most[-\s]popular)\b",
    r"\bonly\b",
    r"\bunique\b",
    r"\bexclusive\b",
    r"\baward[-\s]?winning\b",
    r"\baward winner\b",
    r"#1|\brank\s+1\b|\bnumber\s+one\b",
    # Evaluative marketing voice
    r"\bhighly\s+(?:rated|recommended)\b",
    r"\b(?:customer|local|visitor)\s+favorite\b",
    r"\b(?:perfect|excellent|amazing|fantastic|incredible)\b",
    r"\bdon[’']?t\s+miss\b",
    r"\bmust\s+(?:try|have)\b",
    r"\blocals?\s+love\b",
    r"\blocals?\s+secret\b",
    r"\bworth\s+it\b",
    r"\babsolutely\b",
    r"\blife[-\s]changing\b",
    r"\btransformative\b",
    # False scarcity / urgency
    r"\blimited\s+time\b",
    r"\bwhile\s+supplies\b",
    r"\bspecial\s+deal\b",
    # Comparative
    r"\bbetter\s+than\b",
    r"\bsuperior\s+to\b",
    r"\bbeats\b",
)
"""Spec §3.2 — exhaustive list. Source of truth; integration tests pin the contract."""

_DISALLOWED_REGEX: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in DISALLOWED_PHRASES
)


# ─────────── regime selection ───────────

_SPECIFIC_QUALITY_SUB_INTENTS: frozenset[str] = frozenset(
    {
        "PHONE_LOOKUP",
        "WEBSITE_LOOKUP",
        "HOURS_LOOKUP",
        "LOCATION_LOOKUP",
        "RATING_LOOKUP",
        "REVIEW_COUNT_LOOKUP",
        "TIME_LOOKUP",
        "OPEN_NOW",
    }
)

_GENERIC_CATEGORY_SUB_INTENTS: frozenset[str] = frozenset(
    {"GENERAL_QUESTION", "RECOMMENDATION", "DISCOVERY"}
)

_EMERGENCY_URGENT_SUB_INTENTS: frozenset[str] = frozenset(
    {"DATE_LOOKUP", "NEXT_OCCURRENCE", "AGE_LOOKUP", "COST_LOOKUP", "URGENT_NOW"}
)


def select_placement_regime(intent_result: Any) -> PlacementRegime:
    """Classify a query into a placement regime (spec §1).

    Reads ``mode``, ``sub_intent``, and ``entity`` defensively via
    ``getattr`` so callers can pass anything duck-typed (the real
    ``IntentResult`` from ``app.chat.intent_classifier``, a
    ``SimpleNamespace`` in tests, etc.). Optional fields like
    ``inferred_category`` aren't required by the regime decision itself —
    the caller decides whether organic catalog rows exist.

    Defaults to ``SPECIFIC_QUALITY`` when the intent doesn't match a
    sponsored-eligible shape: zero-sponsored is the safe failure mode.
    """
    mode = getattr(intent_result, "mode", None)
    if mode != "ask":
        return PlacementRegime.SPECIFIC_QUALITY

    sub = getattr(intent_result, "sub_intent", None) or ""
    entity = getattr(intent_result, "entity", None) or getattr(
        intent_result, "entity_resolved", None
    )

    if sub in _SPECIFIC_QUALITY_SUB_INTENTS:
        return PlacementRegime.SPECIFIC_QUALITY
    if sub in _EMERGENCY_URGENT_SUB_INTENTS:
        return PlacementRegime.EMERGENCY_URGENT
    if sub in _GENERIC_CATEGORY_SUB_INTENTS and not entity:
        return PlacementRegime.GENERIC_CATEGORY

    return PlacementRegime.SPECIFIC_QUALITY


# ─────────── feature flag ───────────


def is_renderer_enabled() -> bool:
    """Return True only when ``FEATURE_FLAG_DISCLOSURE_RENDERER=true`` (case-insensitive)."""
    return os.environ.get(FEATURE_FLAG_ENV_VAR, "").strip().lower() == "true"


# ─────────── eligibility + selection ───────────


def _temporal_overlap(
    starts_at: datetime | None,
    ends_at: datetime | None,
    date_context: datetime | None,
) -> bool:
    """Return True if ``date_context`` falls inside ``[starts_at, ends_at]``.

    Open bounds (``None``) are treated as "no constraint on that side".
    Returns True when ``date_context`` is None — the caller hasn't given
    us anything to gate on, so we don't reject the sponsor for that
    reason. A naive ``date_context`` is interpreted as America/Phoenix
    wall time (``LAKE_HAVASU_TZ``).
    """
    if date_context is None:
        return True
    dc = date_context
    if dc.tzinfo is None:
        dc = dc.replace(tzinfo=LAKE_HAVASU_TZ)
    if starts_at is not None and dc < starts_at:
        return False
    if ends_at is not None and dc > ends_at:
        return False
    return True


def _eligible(
    sponsor: Sponsor,
    regime: PlacementRegime,
    query_context: dict[str, Any],
) -> bool:
    """Per-regime eligibility gate (spec §1)."""
    if getattr(sponsor, "status", None) != SponsorStatus.LIVE.value:
        return False

    if regime == PlacementRegime.EMERGENCY_URGENT:
        # Strict reliability bar: verified fields must be confirmed.
        # ``getattr`` default False keeps the renderer working before
        # Lane S1's ``verified_fields_present`` migration lands.
        if not getattr(sponsor, "verified_fields_present", False):
            return False
        # Organic pairing is mandatory — sponsored alone is misleading
        # for time-sensitive decisions.
        if not query_context.get("organic_rows"):
            return False
        if not _temporal_overlap(
            getattr(sponsor, "starts_at", None),
            getattr(sponsor, "ends_at", None),
            query_context.get("date_context"),
        ):
            return False

    return True


def _pick_sponsor(candidates: list[Sponsor]) -> Optional[Sponsor]:
    """Deterministic tie-break: highest weight, then earliest ``created_at``.

    Sort key uses negative weight so Python's stable sort keeps an
    unambiguous ordering; ``created_at`` ascending breaks ties (the
    sponsor who's been on platform longest wins).
    """
    if not candidates:
        return None

    def _key(s: Sponsor) -> tuple[int, datetime]:
        weight = int(getattr(s, "weight", 0) or 0)
        created = getattr(s, "created_at", None)
        # Use a far-future fallback so missing ``created_at`` sorts last
        # rather than crashing the sort.
        return (-weight, created or datetime.max)

    ordered = sorted(candidates, key=_key)
    return ordered[0]


# ─────────── body / attribution / cta builders ───────────


def _build_attribution(sponsor: Sponsor) -> str:
    """``"{name} — {attribution_text}"`` or just the name if no descriptor."""
    name = (getattr(sponsor, "name", None) or "").strip()
    descriptor = (getattr(sponsor, "attribution_text", None) or "").strip()
    if descriptor:
        return f"{name} — {descriptor}"
    return name


def _build_body(sponsor: Sponsor) -> str:
    """Concatenate verified factual descriptors (spec §3.1).

    Phase 1 reads only the ``Sponsor`` advertiser-supplied fields
    (``headline``, ``pitch``). Provider-linked enrichment
    (``years_in_business``, ``hours``, etc.) is deferred to a later
    slice — when ``business_id`` is set, the renderer can join.
    """
    fragments: list[str] = []
    headline = (getattr(sponsor, "headline", None) or "").strip()
    if headline:
        fragments.append(headline.rstrip(".") + ".")
    pitch = (getattr(sponsor, "pitch", None) or "").strip()
    if pitch:
        fragments.append(pitch.rstrip(".") + ".")
    return " ".join(fragments).strip()


def _build_cta(sponsor: Sponsor) -> Optional[str]:
    """Return ``"Label [URL](URL)"`` or None when CTA is unusable.

    Spec §2.2: URL must have ``http://`` or ``https://`` scheme; missing
    label or URL suppresses the CTA entirely.
    """
    label = (getattr(sponsor, "cta_label", None) or "").strip()
    url = (getattr(sponsor, "cta_url", None) or "").strip()
    if not label or not url:
        return None
    if not (url.startswith("http://") or url.startswith("https://")):
        return None
    return f"{label} [{url}]({url})"


# ─────────── tone allowlist check ───────────


def _check_tone_allowlist(disclosure_word: str, body: str, attribution: str) -> bool:
    """Return True iff body + attribution contain no disallowed phrases.

    The disclosure word is whitelisted by construction — it's a module
    constant and never participates in the regex scan. We only screen
    advertiser-supplied text.
    """
    combined = f"{body} {attribution}"
    for pattern in _DISALLOWED_REGEX:
        if pattern.search(combined):
            return False
    return True


# ─────────── public renderer ───────────


def render_with_decision(
    regime: PlacementRegime,
    candidate_sponsors: list[Sponsor],
    *,
    query_context: Optional[dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> tuple[Optional[SponsoredBlock], RenderDecision]:
    """Render a sponsored block AND return the decision telemetry.

    Lane P2.OBS.1 — canonical implementation. ``render_sponsored_block``
    is a thin wrapper that discards the decision for back-compat with
    callers that don't need it. New call sites (Tier 3 handler)
    should prefer this function so the decision can be persisted via
    ``record_decision`` for the chat-log writer to consume.

    Returns ``(block, decision)``:
    - ``block`` is None when sponsored is suppressed for any of: regime
      ``SPECIFIC_QUALITY``, no candidates, all candidates fail eligibility,
      body assembled from verified fields is empty, tone allowlist rejects.
    - ``decision`` is always populated; see :class:`RenderDecision` for
      field semantics.

    Deterministic for fixed inputs. ``db`` is accepted for API symmetry
    but currently unused — provider-linked enrichment is a later slice.
    """
    if regime == PlacementRegime.SPECIFIC_QUALITY:
        return None, RenderDecision(regime=regime)
    if not candidate_sponsors:
        return None, RenderDecision(regime=regime)

    ctx = query_context or {}

    eligible = [s for s in candidate_sponsors if _eligible(s, regime, ctx)]
    if not eligible:
        return None, RenderDecision(regime=regime, eligible=False)

    sponsor = _pick_sponsor(eligible)
    if sponsor is None:
        return None, RenderDecision(regime=regime, eligible=False)

    sponsor_id = str(getattr(sponsor, "id", "")) or None
    attribution = _build_attribution(sponsor)
    body = _build_body(sponsor)
    if not body or not attribution:
        return None, RenderDecision(
            regime=regime, eligible=True, sponsor_id=sponsor_id
        )

    tone_passed = _check_tone_allowlist(DISCLOSURE_WORD, body, attribution)
    if not tone_passed:
        return None, RenderDecision(
            regime=regime,
            eligible=True,
            sponsor_id=sponsor_id,
            tone_allowlist_passed=False,
        )

    block = SponsoredBlock(
        disclosure_word=DISCLOSURE_WORD,
        body=body,
        cta=_build_cta(sponsor),
        attribution=attribution,
        sponsor_id=sponsor_id or "",
        regime=regime,
    )
    return block, RenderDecision(
        regime=regime,
        eligible=True,
        sponsor_id=sponsor_id,
        tone_allowlist_passed=True,
    )


def render_sponsored_block(
    regime: PlacementRegime,
    candidate_sponsors: list[Sponsor],
    *,
    query_context: Optional[dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> Optional[SponsoredBlock]:
    """Render a sponsored block, or return None when sponsored is suppressed.

    Back-compat wrapper around :func:`render_with_decision` — discards
    the telemetry decision. New call sites should prefer the decision-
    aware variant.
    """
    block, _ = render_with_decision(
        regime,
        candidate_sponsors,
        query_context=query_context,
        db=db,
    )
    return block


# ─────────── decision context (Lane P2.OBS.1 telemetry plumbing) ───────────


_render_decision_ctx: ContextVar[Optional[RenderDecision]] = ContextVar(
    "_render_decision_ctx", default=None
)
"""Request-scoped slot for the most recent RenderDecision.

The Tier 3 handler computes a decision deep in the call stack, but the
``log_unified_route`` writer is invoked from the unified router at the
end of request handling and doesn't see the handler's return tuple
(extending that signature would ripple across ~25 test sites that
unpack ``text, _, _, _ = answer_with_tier3(...)``). The contextvar
bridges the two without changing handler signatures.

Pattern:
- :func:`record_decision` sets the slot inside the renderer integration.
- :func:`consume_decision` reads-and-clears in the chat-log writer.
- :func:`reset_decision_context` is called at request entry by the
  unified router as a defensive belt-and-suspenders against stale state
  on a reused thread-pool worker — ``consume_decision`` already clears
  on read, but a request that errors before reaching the writer would
  leave the slot populated for the next turn on this thread.
"""


def record_decision(decision: RenderDecision) -> None:
    """Store this turn's RenderDecision in the request context."""
    _render_decision_ctx.set(decision)


def consume_decision() -> Optional[RenderDecision]:
    """Return the recorded decision and clear the slot (one-shot)."""
    decision = _render_decision_ctx.get()
    if decision is not None:
        _render_decision_ctx.set(None)
    return decision


def reset_decision_context() -> None:
    """Clear the slot. Call at request entry to defeat thread-pool reuse."""
    _render_decision_ctx.set(None)
