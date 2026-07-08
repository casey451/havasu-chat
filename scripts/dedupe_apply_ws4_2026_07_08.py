"""WS4 phone-signal dedup APPLY (gated, reversible) — 2026-07-08.

Re-runs the S1 clustering engine (now with the phone-twin signal + thin-row gate +
richness keeper rule) over all active providers and applies EXACTLY the
Casey-approved set:

  * every ``duplicate`` cluster  -> retire the clone(s) via
    ``provider_merge.merge_providers`` (soft is_active=False + attributes.
    merged_into_slug so ``/provider/<old>`` 301s to the keeper, gap-fill, FK
    repoint, DedupeResolution 'merged').
  * FOUR audit-confirmed ``multi_location`` twins UPGRADED to retire (address
    variants of the same place): ``_UPGRADE_RETIRE_SLUGS``.

Deliberately NOT touched (outside the approval): every other ``multi_location``
cluster (the 3 unrelated brands stay keep-both, NOT grouped here) and every
``parent_child`` cluster. So the ONLY writes are the approved retirements.

DRY-RUN by default (prints the retire plan + counts). ``--apply`` writes and emits
an undo CSV. Runs in CI (repo .env → internal DATABASE_URL). Idempotent: a clone
already retired (inactive) is skipped, so a second --apply run writes 0.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.dedupe.cluster import ProviderRecord, cluster_providers  # noqa: E402

_UNDO_CSV = "dedupe_apply_ws4_undo_2026-07-08.csv"

# Audit-confirmed same-place twins the engine classifies multi_location only
# because the GLH twin carries a differing address. Casey approved upgrading these
# FOUR to retire (address variants only). Slug = the row to RETIRE.
_UPGRADE_RETIRE_SLUGS: frozenset[str] = frozenset(
    {
        "bad-miguel-s",
        "hangar-24-taproom-restaurant",
        "the-office-cocktail-lounge",
        "filiberto-s-mexican-food",
    }
)


def _load_records(db) -> list[ProviderRecord]:
    rows = db.execute(
        select(
            Provider.id, Provider.provider_name, Provider.address, Provider.phone,
            Provider.google_place_id, Provider.google_review_count, Provider.verified,
            Provider.slug, Provider.website,
        ).where(Provider.is_active.is_(True))
    ).all()
    return [
        ProviderRecord(
            id=str(r.id), name=r.provider_name or "", address=r.address, phone=r.phone,
            google_place_id=r.google_place_id, review_count=int(r.google_review_count or 0),
            verified=bool(r.verified), slug=r.slug, website=r.website,
        )
        for r in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the WS4 phone-signal dedup retirements.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)
    dry = not args.apply

    retired = skipped = 0
    undo_rows: list[dict] = []

    with SessionLocal() as db:
        clusters = cluster_providers(_load_records(db))
        dup_clusters = [c for c in clusters if c.relationship_type == "duplicate"]
        ml_clusters = [c for c in clusters if c.relationship_type == "multi_location"]
        print(f"clusters: {len(clusters)} | duplicate: {len(dup_clusters)} | multi_location: {len(ml_clusters)}\n")

        def _retire(primary: Provider, clone_rec: ProviderRecord, tag: str) -> None:
            nonlocal retired, skipped
            dup = db.get(Provider, clone_rec.id)
            if dup is None or not dup.is_active:
                return  # idempotent: already retired
            print(f"  RETIRE [{tag}] {dup.provider_name!r} ({dup.slug}) -> {primary.provider_name!r} ({primary.slug})")
            undo_rows.append(
                {"action": "retire", "id": dup.id, "keep_id": primary.id,
                 "retire_slug": dup.slug or "", "keep_slug": primary.slug or "",
                 "provider_name": dup.provider_name or "", "old_is_active": dup.is_active}
            )
            if not dry:
                try:
                    merge_providers(db, keep_id=str(primary.id), dup_id=str(dup.id))
                    db.commit()
                except ValueError as e:  # operator-sourced / invalid -> skip, don't fail the batch
                    db.rollback()
                    skipped += 1
                    print(f"    SKIP ({e})")
                    return
            retired += 1

        # 1) every duplicate cluster -> retire clones.
        for c in dup_clusters:
            primary = db.get(Provider, c.primary.id)
            if primary is None:
                skipped += 1
                continue
            for clone in c.clones:
                _retire(primary, clone, "duplicate")

        # 2) the four approved multi_location upgrades -> retire the named twin only.
        for c in ml_clusters:
            primary = db.get(Provider, c.primary.id)
            if primary is None:
                continue
            for clone in c.clones:
                if clone.slug in _UPGRADE_RETIRE_SLUGS:
                    _retire(primary, clone, "upgrade")

    if not dry and undo_rows:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f, fieldnames=["action", "id", "keep_id", "retire_slug", "keep_slug",
                               "provider_name", "old_is_active"]
            )
            w.writeheader()
            w.writerows(undo_rows)

    print(f"\nretired={retired}  skipped={skipped}  (expected 15: 11 duplicate + 4 upgrade)")
    if dry:
        print("DRY RUN — no DB writes. Re-run with --apply after confirming the retire list (prod-data gate).")
    else:
        print(f"APPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
