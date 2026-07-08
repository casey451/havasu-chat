"""Merge one live duplicate Provider into another (Item C).

The cross-source dedup audit (scripts/cross_source_dedup_audit.py) finds pairs of
already-live providers that are the same real-world business. This module is the
write half: a single, tested primitive that folds the ``dup`` provider into the
``keep`` provider and retires the loser, so consumption surfaces show ONE row.

Design (matches the golakehavasu one-off retire pattern: soft-retire + gap-fill,
never hard-delete):

  1. Gap-fill keeper scalar fields from the dup (never clobber existing data).
  2. Combine source provenance on the keeper (and its Entity).
  3. Re-sync the keeper's ENTITY graph from the enriched legacy row.
  4. Repoint every inbound reference from the loser to the keeper:
       * provider-level FKs: Event.provider_id, Program.provider_id,
         Contribution.created_provider_id, AnalyticsEvent.provider_id
       * entity-level FKs (loser.entity_id -> keeper.entity_id): Event.entity_id,
         Program.entity_id, Photo.entity_id, PeerRecommendation.entity_id, and
         UserFavorite / Claim (which carry a UNIQUE(user_id, entity_id) -- collisions
         are de-duplicated rather than repointed).
  5. Soft-retire the loser: Provider.is_active=False, pending_review=False,
     draft=True (removed from every consumption query, which filters
     draft=False / is_active), and its Entity.is_active=False.

The loser row is kept as a tombstone (no live inbound references) so analytics
and history survive. Nothing is hard-deleted, so the CASCADE on the ENTITY
extension tables (Location, Hours, ContactPoint, ...) never fires.

Refuses to retire an operator-sourced row (hand-curated is authoritative); pass
the operator row as ``keep`` instead.

ORM models are lazy-imported to avoid the import cycle the reconcilers document.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.contrib.ingest_reconciler import _combine_sources

logger = logging.getLogger(__name__)

# Keeper scalar fields gap-filled from the loser (never clobbered). provider_name
# / category / slug are intentionally excluded: the keeper keeps its identity.
_GAP_FILL_FIELDS: tuple[str, ...] = (
    "address",
    "phone",
    "email",
    "website",
    "facebook",
    "hours",
    "hours_structured",
    "description",
    "lat",
    "lng",
    "google_place_id",
    "zip",
    "district",
    "google_primary_category",
    "google_categories",
    "google_rating",
    "google_review_count",
    "google_review_snippets",
    "google_photo_refs",
    "google_photo_urls",
    "google_hours",
)

# Operational / merge-internal ``attributes`` keys that must NEVER transfer from a
# retired loser to the keeper during the per-key attributes gap-fill (they describe
# the loser's own lifecycle, not curated content about the business).
_ATTRS_GAP_FILL_DENYLIST: frozenset[str] = frozenset(
    {"merged_into_slug", "address_flag_dismissed"}
)


@dataclass
class MergeResult:
    keep_id: str
    dup_id: str
    gap_filled: list[str] = field(default_factory=list)
    repointed: dict[str, int] = field(default_factory=dict)
    combined_source: str | None = None
    dry_run: bool = False


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def merge_providers(
    db: Session,
    *,
    keep_id: str,
    dup_id: str,
    dry_run: bool = False,
) -> MergeResult:
    """Fold ``dup`` into ``keep`` and soft-retire ``dup``. Caller commits.

    Raises ``ValueError`` for invalid inputs (same id, missing row, missing
    entity, or attempting to retire an operator-sourced row). On ``dry_run`` the
    function computes and returns the plan (gap_filled / repointed counts) but
    makes no mutations.
    """
    from app.db.entity_dual_write import sync_provider_entity_from_legacy
    from app.db.models import (
        AnalyticsEvent,
        Claim,
        Contribution,
        Entity,
        Event,
        PeerRecommendation,
        Photo,
        Program,
        Provider,
        UserFavorite,
    )

    if keep_id == dup_id:
        raise ValueError("keep_id and dup_id are the same provider")

    keep = db.get(Provider, keep_id)
    dup = db.get(Provider, dup_id)
    if keep is None:
        raise ValueError(f"keep provider not found: {keep_id}")
    if dup is None:
        raise ValueError(f"dup provider not found: {dup_id}")
    if not keep.entity_id:
        raise ValueError(f"keep provider has no entity_id: {keep_id}")
    if not dup.entity_id:
        raise ValueError(f"dup provider has no entity_id: {dup_id}")
    if (dup.source or "").strip() == "operator":
        raise ValueError("refusing to retire an operator-sourced provider; pass it as keep_id")

    result = MergeResult(keep_id=keep_id, dup_id=dup_id, dry_run=dry_run)

    # 1. Gap-fill keeper scalars from the loser (never clobber).
    #
    # ``google_place_id`` is a MOVE, not a copy: the partial unique index
    # ``ux_providers_google_place_id`` (e9f0a1b2c3d4) spans retired rows too,
    # so the value must leave the loser before (or in the same flush as) it
    # lands on the keeper — clear-then-flush-then-set keeps the per-statement
    # uniqueness check happy on Postgres.
    for f in _GAP_FILL_FIELDS:
        if _is_empty(getattr(keep, f, None)) and not _is_empty(getattr(dup, f, None)):
            result.gap_filled.append(f)
            if not dry_run:
                value = getattr(dup, f)
                if f == "google_place_id":
                    dup.google_place_id = None
                    db.flush()
                setattr(keep, f, value)

    # 1b. Gap-fill CURATED attributes per-key (never clobber). The keeper inherits
    # each of the loser's ``attributes`` keys where its own value is empty, so an
    # operator-approved cuisine — or any future curated key — survives the merge
    # instead of dying with the retired twin. (WS4 2026-07-08: hangar-24-taproom's
    # client-assigned 'american' was lost because ``attributes`` wasn't gap-filled;
    # this makes WS12-era curated data survive merges by construction.) Merge-
    # internal / operational keys never transfer.
    dup_attrs = dup.attributes if isinstance(dup.attributes, dict) else {}
    keep_attrs = dict(keep.attributes) if isinstance(keep.attributes, dict) else {}
    inherited = {
        k: v
        for k, v in dup_attrs.items()
        if k not in _ATTRS_GAP_FILL_DENYLIST
        and not _is_empty(v)
        and _is_empty(keep_attrs.get(k))
    }
    if inherited:
        result.gap_filled.append("attributes")
        if not dry_run:
            keep_attrs.update(inherited)
            keep.attributes = keep_attrs

    # 2. Combine source provenance on the keeper.
    combined = _combine_sources(keep.source, dup.source or "")
    result.combined_source = combined
    if not dry_run:
        keep.source = combined

    # Count inbound references (so dry-run reports the blast radius).
    keep_ent, dup_ent = keep.entity_id, dup.entity_id

    def _count(model: Any, attr: str, value: str) -> int:
        col = getattr(model, attr)
        return int(db.scalar(select(func.count()).select_from(model).where(col == value)) or 0)

    # Provider-level FKs: loser provider id -> keeper provider id.
    # ``Provider.parent_provider_id`` rides along (Track B1): department
    # children of a merged-away parent re-home onto the keeper.
    provider_fk = [
        (Event, "provider_id"),
        (Program, "provider_id"),
        (Contribution, "created_provider_id"),
        (AnalyticsEvent, "provider_id"),
        (Provider, "parent_provider_id"),
    ]
    # Entity-level FKs without a uniqueness constraint: loser entity -> keeper entity.
    entity_fk_plain = [
        (Event, "entity_id"),
        (Program, "entity_id"),
        (Photo, "entity_id"),
        (PeerRecommendation, "entity_id"),
    ]
    # Entity-level FKs WITH UNIQUE(user_id, entity_id): repoint or de-dupe.
    entity_fk_unique = [UserFavorite, Claim]

    for model, attr in provider_fk:
        n = _count(model, attr, dup_id)
        if n:
            result.repointed[f"{model.__tablename__}.{attr}"] = n
            if not dry_run:
                for row in db.scalars(select(model).where(getattr(model, attr) == dup_id)).all():
                    setattr(row, attr, keep_id)

    for model, attr in entity_fk_plain:
        n = _count(model, attr, dup_ent)
        if n:
            result.repointed[f"{model.__tablename__}.{attr}"] = n
            if not dry_run:
                for row in db.scalars(select(model).where(getattr(model, attr) == dup_ent)).all():
                    setattr(row, attr, keep_ent)

    for model in entity_fk_unique:
        rows = db.scalars(select(model).where(model.entity_id == dup_ent)).all()
        if not rows:
            continue
        existing_users = {
            uid
            for (uid,) in db.execute(select(model.user_id).where(model.entity_id == keep_ent)).all()
        }
        moved = deduped = 0
        for row in rows:
            if row.user_id in existing_users:
                deduped += 1
                if not dry_run:
                    db.delete(row)
            else:
                existing_users.add(row.user_id)
                moved += 1
                if not dry_run:
                    row.entity_id = keep_ent
        if moved:
            result.repointed[f"{model.__tablename__}.entity_id"] = moved
        if deduped:
            result.repointed[f"{model.__tablename__}.entity_id(deduped)"] = deduped

    # 3. Re-sync keeper ENTITY graph + combine source on keeper Entity.
    if not dry_run:
        sync_provider_entity_from_legacy(db, keep)
        keep_entity = db.get(Entity, keep_ent)
        if keep_entity is not None:
            keep_entity.source = _combine_sources(keep_entity.source, dup.source or "")[:64]

    # 4. Soft-retire the loser (provider + its Entity), stamping the slug
    # redirect so /provider/<old-slug> 301s to the survivor (the P1.10
    # mechanism in app/providers/router.py — previously only the
    # merge_duplicate_provider_slugs.py batch path set it).
    if not dry_run:
        dup.is_active = False
        dup.pending_review = False
        dup.draft = True
        if keep.slug:
            attrs = dict(dup.attributes or {})
            attrs["merged_into_slug"] = keep.slug
            dup.attributes = attrs
        dup_entity = db.get(Entity, dup_ent)
        if dup_entity is not None:
            dup_entity.is_active = False

    # 5. Record the pair as resolved (Track B1): the dedupe review queue
    # computes candidates live, so without this the merged pair would
    # resurface if the loser were ever reactivated. Upserts on pair_key —
    # a prior human resolution is superseded by the actual merge.
    if not dry_run:
        from app.db.models import DedupeResolution, dedupe_pair_key

        key = dedupe_pair_key(keep_id, dup_id)
        existing = db.scalar(
            select(DedupeResolution).where(DedupeResolution.pair_key == key)
        )
        if existing is not None:
            existing.resolution = "merged"
        else:
            lo, hi = sorted((keep_id, dup_id))
            db.add(
                DedupeResolution(
                    pair_key=key,
                    provider_id_a=lo,
                    provider_id_b=hi,
                    resolution="merged",
                )
            )

    logger.info(
        "merge_providers %s <- %s (dry_run=%s) gap_filled=%s repointed=%s",
        keep_id,
        dup_id,
        dry_run,
        result.gap_filled,
        result.repointed,
    )
    return result
