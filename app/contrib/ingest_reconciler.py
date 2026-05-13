"""Cross-layer ingest reconciler.

Each new :class:`~app.contrib.ingest_base.EntityPayload` from any layer
(Google / OSM / city / specialized) is reconciled against existing entities
before write. Three match strategies in priority order:

1. ``google_place_id`` exact match (definitive when both payload and existing
   location row have it)
2. Geo proximity (within :data:`GEO_PROXIMITY_THRESHOLD_M`) **and** normalized
   name match → ``update``; geo proximity with name mismatch → ``ambiguous``
3. Normalized name only (no qualifying geo) → ``ambiguous``

Field-merge priority: operator-typed > Google > OSM > city > specialized.

Returns :class:`ReconcileResult` metadata only; callers perform
``session.add(Provider(...))`` / ``session.merge`` / sync helpers — reconciler
does not write catalog rows (Phase 1D ``before_flush`` stays authoritative).

ORM models are lazy-imported inside functions to avoid import-cycle gotcha #17.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any

from sqlalchemy.orm import Session

from app.contrib.ingest_base import EntityPayload

logger = logging.getLogger(__name__)

GEO_PROXIMITY_THRESHOLD_M = 50.0
SOURCE_PRIORITY: dict[str, int] = {
    "operator": 0,
    "google_places": 1,
    "osm": 2,
    "lhc_open_data": 3,
    "az_roc": 3,
    "npi_registry": 4,
    "usapickleball": 4,
    "pdga": 4,
}


@dataclass
class ReconcileResult:
    action: str
    existing_id: str | None = None
    merge_fields: dict[str, Any] | None = None
    reason: str | None = None


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(min(1.0, sqrt(a)))


def slugify(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def _min_priority_for_source_string(source: str | None) -> int:
    parts = [p.strip() for p in (source or "").split(",") if p.strip()]
    if not parts:
        return 99
    return min(SOURCE_PRIORITY.get(p, 99) for p in parts)


def _combine_sources(existing: str | None, incoming: str) -> str:
    """Comma-separated provenance, ordered by SOURCE_PRIORITY (lower first)."""
    tokens = [p.strip() for p in (existing or "").split(",") if p.strip()]
    if incoming not in tokens:
        tokens.append(incoming)
    tokens.sort(key=lambda s: SOURCE_PRIORITY.get(s, 99))
    return ",".join(tokens)


def reconcile_hit(db: Session, payload: EntityPayload) -> ReconcileResult:
    from app.db.models import Entity, Location

    if payload.google_place_id:
        loc = (
            db.query(Location)
            .filter(Location.google_place_id == payload.google_place_id)
            .first()
        )
        if loc:
            return ReconcileResult(
                action="update",
                existing_id=loc.entity_id,
                merge_fields=_compute_merge_fields(db, loc.entity_id, payload),
                reason="google_place_id exact match",
            )

    if payload.lat is not None and payload.lng is not None:
        candidates = (
            db.query(Location)
            .filter(
                Location.lat.isnot(None),
                Location.lng.isnot(None),
            )
            .all()
        )
        nearby: list[Any] = []
        for cand in candidates:
            if haversine_m(payload.lat, payload.lng, cand.lat, cand.lng) <= GEO_PROXIMITY_THRESHOLD_M:
                nearby.append(cand)
        name_matches: list[Any] = []
        for cand in nearby:
            ent = db.get(Entity, cand.entity_id)
            if ent and slugify(ent.name) == slugify(payload.name):
                name_matches.append(cand)
        if len(name_matches) == 1:
            cand = name_matches[0]
            return ReconcileResult(
                action="update",
                existing_id=cand.entity_id,
                merge_fields=_compute_merge_fields(db, cand.entity_id, payload),
                reason="geo within 50m + name match",
            )
        if len(name_matches) > 1:
            return ReconcileResult(
                action="ambiguous",
                existing_id=name_matches[0].entity_id,
                reason="multiple entities within 50m with matching name",
            )
        if nearby:
            return ReconcileResult(
                action="ambiguous",
                existing_id=nearby[0].entity_id,
                reason="geo within 50m but name differs",
            )

    slug = slugify(payload.name)
    if slug:
        for cand in db.query(Entity).filter(Entity.name.isnot(None)).all():
            if slugify(cand.name) == slug:
                return ReconcileResult(
                    action="ambiguous",
                    existing_id=cand.id,
                    reason="name match only (no geo)",
                )

    return ReconcileResult(action="insert", reason="no match")


def _compute_merge_fields(db: Session, existing_id: str, payload: EntityPayload) -> dict[str, Any]:
    from app.db.models import Entity

    ent = db.get(Entity, existing_id)
    if not ent:
        return {}
    if ent.source == "operator":
        return {}

    new_pri = SOURCE_PRIORITY.get(payload.source, 99)
    existing_pri = _min_priority_for_source_string(ent.source)

    if new_pri < existing_pri:
        merged_source = _combine_sources(ent.source, payload.source)
        return {
            "name": payload.name,
            "description": payload.description,
            "source": merged_source,
        }
    if new_pri > existing_pri:
        merge: dict[str, Any] = {}
        if not ent.description and payload.description:
            merge["description"] = payload.description
        return merge
    return {}


def log_ambiguous_reconcile(result: ReconcileResult, *, context: str = "") -> None:
    if result.action != "ambiguous":
        return
    msg = f"ingest_reconcile ambiguous ({result.reason})"
    if context:
        msg = f"{msg} [{context}]"
    logger.warning(msg, extra={"existing_id": result.existing_id})
