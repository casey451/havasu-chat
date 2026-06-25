"""Central cross-source event reconciler -- ONE dedup path for all event scrapers.

Every event scraper (river_scene, golakehavasu, future city calendar) routes an
:class:`~app.events.scrapers.base.EventPayload` through :func:`reconcile_event`
*before* creating a contribution / Event, so the same farmers market or
London Bridge Days does not get double-booked across sources.

This composes the existing Phase 9b primitives in :mod:`app.events.dedup`
(``find_duplicate`` / ``resolve_venue_entity_id``) rather than re-implementing
fuzzy matching, and adds the two things those primitives lack:

  * ``source_url`` exact match (same-source re-import) -- previously only
    river_scene_pull had this, via its bespoke ``_duplicate_rs_article_import``.
  * Source-priority merge precedence (``EVENT_SOURCE_PRIORITY``) so the richer /
    more authoritative record wins on display fields while useful fields are
    unioned and provenance is combined.

Like :mod:`app.contrib.ingest_reconciler` (the provider reconciler), this
returns :class:`EventReconcileResult` metadata only and never writes catalog
rows -- callers perform the contribution insert / Event merge.

Match strategies, in priority order:

1. ``source_url`` exact (same source re-import)            -> ``update``
2. ``find_duplicate`` hit (same date + fuzzy title + time
   window + venue scoping; Phase 9b semantics)             -> ``duplicate``
3. Same date + venue match but only loose title similarity -> ``ambiguous``
4. Otherwise                                               -> ``insert``

ORM models are lazy-imported inside functions to avoid import cycles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.contribution_store import normalize_submission_url
from app.events.dedup import (
    DEDUP_TITLE_FUZZY_THRESHOLD,
    find_duplicate,
    resolve_venue_entity_id,
)
from app.events.scrapers.base import EventPayload, normalize_event_title

logger = logging.getLogger(__name__)

# rapidfuzz token_sort_ratio is on a 0-100 scale (matches dedup.py).
TITLE_AMBIGUOUS_FLOOR = 55

EVENT_SOURCE_PRIORITY: dict[str, int] = {
    "operator": 0,
    "admin": 0,
    "go_lake_havasu": 1,
    "chamber": 2,
    "lhc_parks_rec": 3,
    "lhc_library": 3,
    "city": 3,
    "river_scene": 4,
    "river_scene_import": 4,
    "seed": 5,
    "user": 5,
    "user_submission": 5,
    # Vision-LLM image scrapers: residue sources -- they contribute the items no
    # richer feed carries, so on a clash they lose to WebTrac/aquatic/civic.
    "parks_rec_calendar": 6,
    "parks_rec_flyers": 6,
    "senior_center_flyers": 6,
}
_UNKNOWN_PRIORITY = 9


@dataclass
class EventReconcileResult:
    action: str  # insert | update | duplicate | ambiguous
    existing_id: str | None = None
    merge_fields: dict[str, Any] | None = None
    reason: str | None = None
    combined_source: str | None = None


def _priority_of(source: str | None) -> int:
    return EVENT_SOURCE_PRIORITY.get((source or "").strip(), _UNKNOWN_PRIORITY)


def _min_priority_for_source_string(source: str | None) -> int:
    parts = [p.strip() for p in (source or "").split(",") if p.strip()]
    if not parts:
        return _UNKNOWN_PRIORITY
    return min(_priority_of(p) for p in parts)


def combine_sources(existing: str | None, incoming: str) -> str:
    """Comma-separated provenance, ordered by EVENT_SOURCE_PRIORITY (lower first)."""
    tokens = [p.strip() for p in (existing or "").split(",") if p.strip()]
    incoming = (incoming or "").strip()
    if incoming and incoming not in tokens:
        tokens.append(incoming)
    tokens.sort(key=_priority_of)
    return ",".join(tokens)


def _payload_source_url(payload: EventPayload) -> str | None:
    return normalize_submission_url(payload.source_stable_url or payload.event_url)


def _compute_merge_fields(
    existing: Any,
    payload: EventPayload,
    *,
    combined_source: str,
) -> dict[str, Any]:
    """Per-priority merge plan for an existing Event vs an incoming payload."""
    if getattr(existing, "operator_override", False) or existing.source == "operator":
        # Hand-curated rows are authoritative: only append provenance.
        return {"source": combined_source}

    new_pri = _priority_of(payload.source)
    existing_pri = _min_priority_for_source_string(existing.source)
    merge: dict[str, Any] = {"source": combined_source}

    incoming_desc = (payload.description or "").strip()
    incoming_url = (payload.event_url or "").strip()
    incoming_src_url = _payload_source_url(payload)

    if new_pri < existing_pri:
        # Incoming is the higher-trust source: it wins on display fields.
        if payload.name:
            merge["title"] = payload.name.strip()
            merge["normalized_title"] = normalize_event_title(payload.name)
        if incoming_desc:
            merge["description"] = incoming_desc
        if payload.venue_name:
            merge["location_name"] = payload.venue_name.strip()
            merge["location_normalized"] = payload.venue_name.lower().strip()
        if incoming_url:
            merge["event_url"] = incoming_url

    # Gap-fill (regardless of direction): never overwrite existing data.
    if incoming_desc and not (existing.description or "").strip():
        merge.setdefault("description", incoming_desc)
    if incoming_url and not (existing.event_url or "").strip():
        merge.setdefault("event_url", incoming_url)
    if incoming_src_url and not existing.source_url:
        merge["source_url"] = incoming_src_url
    if payload.end_time is not None and existing.end_time is None:
        merge["end_time"] = payload.end_time
    if (
        payload.end_date is not None
        and existing.end_date is None
        and payload.end_date > existing.date
    ):
        merge["end_date"] = payload.end_date

    return merge


def _ambiguous_same_venue_candidate(
    db: Session,
    payload: EventPayload,
    venue_entity_id: str | None,
) -> tuple[Any, float] | None:
    """Same-date + same-venue event whose title is only loosely similar.

    Flags the "same place, same day, unclear if the same event" case for human
    review instead of silently inserting a possible double-book.
    """
    from app.db.models import Event

    norm = normalize_event_title(payload.name)
    p_loc = (payload.venue_name or "").lower().strip()
    candidates = list(db.scalars(select(Event).where(Event.date == payload.start_date)).all())
    best: tuple[Any, float] | None = None
    for cand in candidates:
        same_venue = bool(venue_entity_id) and cand.entity_id == venue_entity_id
        if not same_venue and p_loc:
            same_venue = (cand.location_normalized or "").strip() == p_loc
        if not same_venue:
            continue
        ratio = fuzz.token_sort_ratio(
            normalize_event_title(cand.normalized_title or cand.title), norm
        )
        if TITLE_AMBIGUOUS_FLOOR <= ratio < DEDUP_TITLE_FUZZY_THRESHOLD:
            if best is None or ratio > best[1]:
                best = (cand, ratio)
    return best


def reconcile_event(
    db: Session,
    payload: EventPayload,
    *,
    today: date | None = None,
) -> EventReconcileResult:
    """Match an incoming event payload against existing Events.

    *payload* must carry ``start_date``, ``start_time`` and a name. Callers
    handle persistence (contribution insert / Event merge).
    """
    from app.db.models import Event

    _ = today  # reserved for future symmetry with provider reconciler
    if payload.start_date is None or not (payload.name or "").strip():
        return EventReconcileResult(action="insert", reason="incomplete payload")

    # Strategy 1: same-source re-import keyed on source_url.
    src_url = _payload_source_url(payload)
    if src_url:
        existing = db.scalars(select(Event).where(Event.source_url == src_url)).first()
        if existing is not None:
            combined = combine_sources(existing.source, payload.source)
            return EventReconcileResult(
                action="update",
                existing_id=existing.id,
                merge_fields=_compute_merge_fields(existing, payload, combined_source=combined),
                combined_source=combined,
                reason="source_url exact match",
            )

    # Strategy 2: Phase 9b fuzzy duplicate (date + title + time window + venue).
    venue_entity_id = resolve_venue_entity_id(db, payload.venue_name, payload.address)
    dup = find_duplicate(
        db,
        venue_entity_id=venue_entity_id,
        start_date=payload.start_date,
        start_time_obj=payload.start_time,
        normalized_title=normalize_event_title(payload.name),
    )
    if dup is not None:
        combined = combine_sources(dup.source, payload.source)
        return EventReconcileResult(
            action="duplicate",
            existing_id=dup.id,
            merge_fields=_compute_merge_fields(dup, payload, combined_source=combined),
            combined_source=combined,
            reason="find_duplicate match (date + title + venue)",
        )

    # Strategy 3: same date + venue but only loose title overlap -> review.
    amb = _ambiguous_same_venue_candidate(db, payload, venue_entity_id)
    if amb is not None:
        cand, ratio = amb
        return EventReconcileResult(
            action="ambiguous",
            existing_id=cand.id,
            reason=f"same date + venue but title ratio only {ratio:.0f}",
        )

    return EventReconcileResult(action="insert", reason="no match")


def log_ambiguous_reconcile(result: EventReconcileResult, *, context: str = "") -> None:
    if result.action != "ambiguous":
        return
    msg = f"event_reconcile ambiguous ({result.reason})"
    if context:
        msg = f"{msg} [{context}]"
    logger.warning(msg, extra={"existing_id": result.existing_id})
