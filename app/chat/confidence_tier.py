"""Deterministic confidence-tier classifier (Phase 1 forward dispatch, Lane CT1).

Spec: ``docs/maintainability/ui_data_correctness_spec.md`` §1.2 — the
canonical confidence-band table tied to ``last_verified_at`` and
``verification_method``.

The classifier turns a duck-typed record (``Provider``, ``Event``, or any
object with ``last_verified_at`` + ``verification_method`` attributes)
into a ``ConfidenceAssessment`` carrying the tier, the age of the most
recent verification, the recorded method, and a one-line rationale.

Two failure modes this module forecloses:

1. **Tier drift across the formatter.** Without a single source of truth
   for "how confident are we in this row?", every formatter site
   re-derives the answer from raw datetime arithmetic. This module owns
   the policy.
2. **Hedge-language drift.** When the formatter improvises hedges
   inline, voice consistency degrades. ``hedge_phrase()`` returns the
   canonical fragment per tier; the formatter chooses whether to inline
   it but does not re-author the prose.

The classifier is pure: given the same inputs (record + ``now``) it
always returns the same struct. No randomness, no LLM calls. ``now``
defaults to ``now_lake_havasu()`` so production callers don't accidentally
read a timezone-naive ``datetime.now()``.

Lane CT1 ships this module + tests only. Formatter integration is Lane
CT2 — a separate ship after Lane X2 (Tier 3 integration) lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from app.core.timezone import now_lake_havasu

# ─────────── public constants ───────────


class ConfidenceTier(str, Enum):
    """Tier-of-confidence band for a verified record (spec §1.2)."""

    HIGH = "high"  # owner-verified within 30 days OR scraped within 7 days
    MEDIUM = "medium"  # scraped 7–30 days ago, OR third-party source
    LOW = "low"  # older than threshold, single unverified source, OR no record


# Verification-method canonical values, mirrored from
# ``Provider.verification_method`` (Lane S1, revision f7e8d9c0b1a2).
# Source-of-truth for which strings the classifier knows; anything else
# is treated as "unknown method" and falls through to LOW.
METHOD_MANUAL = "manual"
METHOD_SCRAPER = "scraper"
METHOD_OWNER_CONFIRMED = "owner_confirmed"
METHOD_NPI_REGISTRY = "npi_registry"
METHOD_NONE = "none"

_KNOWN_METHODS: frozenset[str] = frozenset(
    {METHOD_MANUAL, METHOD_SCRAPER, METHOD_OWNER_CONFIRMED, METHOD_NPI_REGISTRY}
)

# Threshold table (spec §1.2). Centralized so a future policy revision
# is a one-line edit.
_HIGH_OWNER_DAYS = 30
_HIGH_MANUAL_DAYS = 30
_HIGH_SCRAPER_DAYS = 7
_HIGH_NPI_DAYS = 30
_MEDIUM_SCRAPER_DAYS = 30
_MEDIUM_TRUSTED_DAYS = 90
_DEFAULT_STALE_THRESHOLD_DAYS = 30


# ─────────── public dataclass ───────────


@dataclass(frozen=True)
class ConfidenceAssessment:
    """Result of ``classify_confidence`` — pure data, safe to pass around.

    Frozen so callers can cache and forward without worrying about
    mutation. The rationale is a short human-readable string useful for
    debug surfaces and admin audit trails; it is **not** intended for
    end-user prose (use ``hedge_phrase`` for that).
    """

    tier: ConfidenceTier
    age_days: Optional[int]
    method: Optional[str]
    rationale: str


# ─────────── hedge phrases ───────────

_HEDGE_HIGH = ""
_HEDGE_MEDIUM = "as of last week"
_HEDGE_LOW = "recommend calling to confirm"


def hedge_phrase(tier: ConfidenceTier) -> str:
    """One-sentence prose hedge fragment per tier (spec §1.2).

    HIGH returns an empty string (speak plainly). MEDIUM returns a
    short temporal qualifier. LOW returns a short call-to-confirm
    fragment. The fragments are deliberately short and non-evaluative;
    the persona-brief blocklist (``docs/persona-brief.md`` §8.1) governs
    whether they are inlined verbatim or post-processed by the caller.

    Returns the empty string for any tier the enum doesn't recognize —
    safer than raising mid-render.
    """
    if tier == ConfidenceTier.HIGH:
        return _HEDGE_HIGH
    if tier == ConfidenceTier.MEDIUM:
        return _HEDGE_MEDIUM
    if tier == ConfidenceTier.LOW:
        return _HEDGE_LOW
    return ""


# ─────────── helpers ───────────


def _resolve_now(now: Optional[datetime]) -> datetime:
    """Return caller-supplied ``now`` or ``now_lake_havasu()``.

    Wrapped so tests can monkey-patch ``now_lake_havasu`` at the module
    level and the classifier picks up the override.
    """
    if now is not None:
        return now
    return now_lake_havasu()


def _age_days(last_verified_at: Optional[datetime], now: datetime) -> Optional[int]:
    """Return integer days between ``last_verified_at`` and ``now``.

    Returns ``None`` when ``last_verified_at`` is missing.
    """
    if last_verified_at is None:
        return None
    delta = now - last_verified_at
    return delta.days


# ─────────── public classifier ───────────


def classify_confidence(
    record: Any,
    *,
    now: Optional[datetime] = None,
) -> ConfidenceAssessment:
    """Pure function — classify a record into a confidence tier.

    Reads ``last_verified_at`` and ``verification_method`` defensively
    via ``getattr`` so the same callable works on ``Provider``,
    ``Event``, or any duck-typed object that pre-dates Lane S1's schema
    additions.

    Returns the tier plus supporting context (``age_days``, ``method``,
    ``rationale``) so the formatter can adapt register without
    re-running the policy.

    Decision rules (spec §1.2):

    - ``last_verified_at`` missing → LOW ("no verification record")
    - ``method == 'none'`` or method missing → LOW (overrides age)
    - ``owner_confirmed`` ≤ 30 days → HIGH
    - ``manual`` ≤ 30 days → HIGH
    - ``scraper`` ≤ 7 days → HIGH
    - ``npi_registry`` ≤ 30 days → HIGH
    - ``scraper`` ≤ 30 days → MEDIUM
    - ``manual`` / ``owner_confirmed`` / ``npi_registry`` ≤ 90 days → MEDIUM
    - else → LOW ("older than threshold")
    """
    last_verified_at = getattr(record, "last_verified_at", None)
    method = getattr(record, "verification_method", None)
    resolved_now = _resolve_now(now)
    age = _age_days(last_verified_at, resolved_now)

    # ── LOW shortcuts: no datetime arithmetic possible, or method opts out
    if age is None:
        return ConfidenceAssessment(
            tier=ConfidenceTier.LOW,
            age_days=None,
            method=method,
            rationale="no verification record",
        )

    if method is None:
        return ConfidenceAssessment(
            tier=ConfidenceTier.LOW,
            age_days=age,
            method=None,
            rationale="method missing",
        )

    if method == METHOD_NONE:
        return ConfidenceAssessment(
            tier=ConfidenceTier.LOW,
            age_days=age,
            method=method,
            rationale="method=none",
        )

    # ── HIGH bands
    if method == METHOD_OWNER_CONFIRMED and age <= _HIGH_OWNER_DAYS:
        return ConfidenceAssessment(
            tier=ConfidenceTier.HIGH,
            age_days=age,
            method=method,
            rationale="owner-verified within 30 days",
        )
    if method == METHOD_MANUAL and age <= _HIGH_MANUAL_DAYS:
        return ConfidenceAssessment(
            tier=ConfidenceTier.HIGH,
            age_days=age,
            method=method,
            rationale="manually verified within 30 days",
        )
    if method == METHOD_SCRAPER and age <= _HIGH_SCRAPER_DAYS:
        return ConfidenceAssessment(
            tier=ConfidenceTier.HIGH,
            age_days=age,
            method=method,
            rationale="scraped within 7 days from primary source",
        )
    if method == METHOD_NPI_REGISTRY and age <= _HIGH_NPI_DAYS:
        return ConfidenceAssessment(
            tier=ConfidenceTier.HIGH,
            age_days=age,
            method=method,
            rationale="NPI-registry validated within 30 days",
        )

    # ── MEDIUM bands
    if method == METHOD_SCRAPER and age <= _MEDIUM_SCRAPER_DAYS:
        return ConfidenceAssessment(
            tier=ConfidenceTier.MEDIUM,
            age_days=age,
            method=method,
            rationale="scraped within 30 days",
        )
    if (
        method in (METHOD_MANUAL, METHOD_OWNER_CONFIRMED, METHOD_NPI_REGISTRY)
        and age <= _MEDIUM_TRUSTED_DAYS
    ):
        return ConfidenceAssessment(
            tier=ConfidenceTier.MEDIUM,
            age_days=age,
            method=method,
            rationale="verified within 90 days",
        )

    # ── default: stale or unknown method
    if method not in _KNOWN_METHODS:
        return ConfidenceAssessment(
            tier=ConfidenceTier.LOW,
            age_days=age,
            method=method,
            rationale="unknown verification method",
        )
    return ConfidenceAssessment(
        tier=ConfidenceTier.LOW,
        age_days=age,
        method=method,
        rationale="older than threshold",
    )


# ─────────── convenience helpers ───────────


def is_stale(
    record: Any,
    *,
    threshold_days: int = _DEFAULT_STALE_THRESHOLD_DAYS,
    now: Optional[datetime] = None,
) -> bool:
    """Return True when ``last_verified_at`` is older than ``threshold_days``.

    Treats a missing ``last_verified_at`` as stale — never-verified rows
    are functionally equivalent to "indefinitely old" for any policy
    that gates on freshness. ``threshold_days`` defaults to 30 (the
    spec's HIGH-band cutoff for owner/manual methods).
    """
    last_verified_at = getattr(record, "last_verified_at", None)
    if last_verified_at is None:
        return True
    age = _age_days(last_verified_at, _resolve_now(now))
    if age is None:
        return True
    return age > threshold_days
