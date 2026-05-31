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
        raise ValueError(
            "refusing to retire an operator-sourced provider; pass it as keep_id"
        )

    result = MergeResult(keep_id=keep_id, dup_id=dup_id, dry_run=dry_run)

    # 1. Gap-fill keeper scalars from the loser (never clobber).
    for f in _GAP_FILL_FIELDS:
        if _is_empty(getattr(keep, f, None)) and not _is_empty(getattr(dup, f, None)):
            result.gap_filled.append(f)
            if not dry_run:
                setattr(keep, f, getattr(dup, f))

    # 2. Combine source provenance on the keeper.
    combined = _combine_sources(keep.source, dup.source or "")
    result.combined_source = combined
    if not dry_run:
        keep.source = combined

    # Count inbound references (so dry-run reports the blast radius).
    keep_ent, dup_ent = keep.entity_id, dup.entity_id

    def _count(model: Any, attr: str, value: str) -> int:
        col = getattr(model, attr)
        return int(
            db.scalar(select(func.count()).select_from(model).where(col == value)) or 0
        )

    # Provider-level FKs: loser provider id -> keeper provider id.
    provider_fk = [
        (Event, "provider_id"),
        (Program, "provider_id"),
        (Contribution, "created_provider_id"),
        (AnalyticsEvent, "provider_id"),
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
                for row in db.scalars(
                    select(model).where(getattr(model, attr) == dup_id)
                ).all():
                    setattr(row, attr, keep_id)

    for model, attr in entity_fk_plain:
        n = _count(model, attr, dup_ent)
        if n:
            result.repointed[f"{model.__tablename__}.{attr}"] = n
            if not dry_run:
                for row in db.scalars(
                    select(model).where(getattr(model, attr) == dup_ent)
                ).all():
                    setattr(row, attr, keep_ent)

    for model in entity_fk_unique:
        rows = db.scalars(
            select(model).where(model.entity_id == dup_ent)
        ).all()
        if not rows:
            continue
        existing_users = {
            uid
            for (uid,) in db.execute(
                select(model.user_id).where(model.entity_id == keep_ent)
            ).all()
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

    # 4. Soft-retire the loser (provider + its Entity).
    if not dry_run:
        dup.is_active = False
        dup.pending_review = False
        dup.draft = True
        dup_entity = db.get(Entity, dup_ent)
        if dup_entity is not None:
            dup_entity.is_active = False

    logger.info(
        "merge_providers %s <- %s (dry_run=%s) gap_filled=%s repointed=%s",
        keep_id,
        dup_id,
        dry_run,
        result.gap_filled,
        result.repointed,
    )
    return result
