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
import os
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any

from sqlalchemy.orm import Session

from app.contrib.ingest_base import EntityPayload
from app.utils.contact_norm import is_identity_domain, norm_domain, norm_phone

logger = logging.getLogger(__name__)

GEO_PROXIMITY_THRESHOLD_M = 50.0
SOURCE_PRIORITY: dict[str, int] = {
    "operator": 0,
    "google_places": 1,
    "osm": 2,
    "lhc_open_data": 3,
    "go_lake_havasu": 3,
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


def _contact_tier_enabled() -> bool:
    """Whether the website/phone contact-match tier runs (read at CALL time).

    BLAST RADIUS: this gate guards a tier inside :func:`reconcile_hit`, which is
    the central reconciler for EVERY provider ingest source (osm, google_places,
    az_roc, npi_registry, etc.). When enabled, a payload whose normalized website
    or phone uniquely matches an existing active Provider will MERGE onto that
    entity even with no geo/name match -- so flipping this on changes dedup
    behavior for all of those sources at once. Default is OFF: an unset / empty /
    falsey env value leaves reconcile_hit behaving exactly as before. Casey opts
    in per-environment by setting INGEST_CONTACT_TIER_ENABLED.
    """
    return os.environ.get("INGEST_CONTACT_TIER_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _contact_match_entity_id(db: Session, payload: EntityPayload) -> str | None:
    """Unique active-Provider entity_id matching the payload's website/phone.

    Identity tier: a shared website domain or phone is a stronger signal than
    geo/name, so this runs just below google_place_id. Candidates are ALL active
    providers (not only google-backed ones, unlike the CVB loader's narrower
    _contact_match). Returns an entity_id only when EXACTLY ONE distinct entity
    matches -- zero or multiple -> None, so the caller falls through to the
    geo/name tiers (high precision: unique match only).
    """
    from app.db.models import Provider

    web = norm_domain(payload.website)
    # A social / aggregator / marketplace / site-builder host is shared by many
    # distinct businesses, so it is not a usable identity key -- drop it and let
    # phone (or the geo/name tiers) decide. Without this, a payload pointing at,
    # say, a facebook.com page would contact-merge onto the one existing provider
    # that happens to carry the same host.
    if web is not None and not is_identity_domain(web):
        web = None
    phone = norm_phone(payload.phone)
    if web is None and phone is None:
        return None

    # Column-only scan: the normalizers run in Python, but hydrating every
    # active Provider as a full ORM object per payload was the dominant cost.
    rows = db.query(Provider.entity_id, Provider.website, Provider.phone).filter(
        Provider.is_active.is_(True), Provider.entity_id.is_not(None)
    )
    matches: set[str] = set()
    for entity_id, prov_website, prov_phone in rows:
        if web is not None and norm_domain(prov_website) == web:
            matches.add(entity_id)
        elif phone is not None and norm_phone(prov_phone) == phone:
            matches.add(entity_id)
    if len(matches) == 1:
        return next(iter(matches))
    return None


def reconcile_hit(db: Session, payload: EntityPayload) -> ReconcileResult:
    from app.db.models import Entity, Location

    if payload.google_place_id:
        loc = db.query(Location).filter(Location.google_place_id == payload.google_place_id).first()
        if loc:
            return ReconcileResult(
                action="update",
                existing_id=loc.entity_id,
                merge_fields=_compute_merge_fields(db, loc.entity_id, payload),
                reason="google_place_id exact match",
            )

    # Contact (website/phone) identity tier -- runs ABOVE geo because a shared
    # website domain or phone number is a stronger identity signal than mere
    # proximity. Gated OFF by default; see _contact_tier_enabled for blast radius
    # (this changes dedup behavior for every provider source when enabled).
    if _contact_tier_enabled():
        contact_id = _contact_match_entity_id(db, payload)
        if contact_id is not None:
            return ReconcileResult(
                action="update",
                existing_id=contact_id,
                merge_fields=_compute_merge_fields(db, contact_id, payload),
                reason="contact (website/phone) exact match",
            )

    if payload.lat is not None and payload.lng is not None:
        # T3.1: bounding-box prefilter in SQL so we stop hauling every Location
        # row into Python for a haversine pass. ~50m is < 0.001 deg lat and
        # < 0.0012 deg lng at 34°N; use a comfortably wider 0.002 box — the
        # exact haversine check below is unchanged and still decides.
        _box = 0.002
        candidates = (
            db.query(Location)
            .filter(
                Location.lat.isnot(None),
                Location.lng.isnot(None),
                Location.lat.between(payload.lat - _box, payload.lat + _box),
                Location.lng.between(payload.lng - _box, payload.lng + _box),
            )
            .all()
        )
        nearby: list[Any] = []
        for cand in candidates:
            if (
                haversine_m(payload.lat, payload.lng, cand.lat, cand.lng)
                <= GEO_PROXIMITY_THRESHOLD_M
            ):
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
