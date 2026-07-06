"""Single safe entry point for ANY scraper writing providers into Ask Hava.

The goal: adding new scrapers should not surface duplicates to users. That holds
only if every source funnels through the same prevention path instead of each
scraper re-implementing insert/merge logic (and forgetting a step). This module
is that funnel.

The contract (see NEW_SCRAPER_CHECKLIST.md):

  1. NORMALIZE the payload first (strip whitespace, "" -> None) so the reconciler
     matches on clean values regardless of how messy a given source is.
  2. RECONCILE against existing rows via ``ingest_reconciler.reconcile_hit``:
       * update     -> merge onto the existing entity (no new row)
       * ambiguous  -> a possible dup we are NOT sure about
       * insert     -> genuinely new
  3. The KEY rule: an ``ambiguous`` decision must land the row HIDDEN
     (``draft=True`` + ``pending_review=True``). Every consumption query filters
     ``draft=False``, so a held row is captured for review but NEVER shown to a
     user as a duplicate. :func:`decide_ingest` surfaces this as ``should_hide``
     so a scraper author cannot forget it.

This module returns DECISIONS; the caller still performs the actual
Provider/Entity write (via app.db.entity_dual_write) so source-specific fields
are preserved. What it guarantees is that the decision -- and the hide-on-doubt
rule -- are identical across every source.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.contrib.address_clean import strip_garbage_address
from app.contrib.ingest_base import EntityPayload
from app.contrib.ingest_reconciler import ReconcileResult, reconcile_hit
from app.contrib.ingest_suppression import is_suppressed_business


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def normalize_payload(payload: EntityPayload) -> EntityPayload:
    """Return a cleaned copy: whitespace stripped, empty strings -> None.

    Cleaning before reconciliation matters because a source that emits ``""`` or
    ``" Joe's Bar "`` would otherwise miss matches (or create near-dup rows) that
    a clean value would catch. Name whitespace is collapsed to single spaces.
    Stored values stay human-readable -- domain/phone canonicalization for
    MATCHING happens inside the reconciler's contact tier, not here, so we do not
    mangle what gets displayed.

    The address also runs through :func:`strip_garbage_address` (S2): a plus-code /
    PO box / leading placeholder / entity-suffix string is dropped to ``None`` so
    ingest never stores a misleading pin. A real-but-partial address (bare city, or
    a street with no house number) is preserved.
    """
    name = _clean(payload.name)
    if name:
        name = " ".join(name.split())
    return replace(
        payload,
        name=name or "",
        address=strip_garbage_address(payload.address),
        phone=_clean(payload.phone),
        website=_clean(payload.website),
        description=_clean(payload.description),
        google_place_id=_clean(payload.google_place_id),
    )


@dataclass
class IngestDecision:
    """What a scraper should do with one payload, after normalization + reconcile."""

    action: str  # "update" | "ambiguous" | "insert" | "skip"
    existing_id: str | None
    should_hide: bool  # True -> write draft=True + pending_review=True (hidden)
    reason: str | None
    payload: EntityPayload  # the NORMALIZED payload the caller should persist
    reconcile: ReconcileResult


def decide_ingest(db: Session, payload: EntityPayload) -> IngestDecision:
    """Normalize, reconcile, and return a uniform decision for the caller.

    ``should_hide`` is True exactly when the reconciler is unsure (``ambiguous``)
    -- the caller MUST honour it (draft=True + pending_review=True) so an
    uncertain row is captured for the admin review queue rather than shown to a
    user. ``update`` means merge onto ``existing_id`` (no new row); ``insert``
    means a genuinely new provider. ``skip`` means the identity is on the durable
    ingest_suppression blocklist -- write NOTHING (no insert, no merge, no
    reactivation of a deactivated row); the caller just counts and moves on.
    """
    clean = normalize_payload(payload)
    # Blocklist check FIRST -- before reconcile -- so a suppressed identity can
    # neither insert a fresh row nor match-and-reactivate a deactivated one.
    # ingest_suppression's module doc calls itself "the blocklist the loaders
    # check FIRST"; enforcing it here means every decide_ingest source inherits
    # it instead of each loader having to remember (golakehavasu_partners_load
    # checks it on its own separate path).
    if is_suppressed_business(clean.name):
        return IngestDecision(
            action="skip",
            existing_id=None,
            should_hide=False,
            reason="suppressed: durable do-not-import blocklist (ingest_suppression)",
            payload=clean,
            reconcile=ReconcileResult(action="skip", reason="suppressed"),
        )
    result = reconcile_hit(db, clean)
    return IngestDecision(
        action=result.action,
        existing_id=result.existing_id,
        should_hide=(result.action == "ambiguous"),
        reason=result.reason,
        payload=clean,
        reconcile=result,
    )
