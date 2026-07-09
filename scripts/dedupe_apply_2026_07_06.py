"""T2.1 apply — resolve the catalog dedupe proposal (gated, reversible).

Re-runs the S1 clustering engine over all active providers (same input as
``scripts.dedupe_catalog``) and APPLIES the approved resolutions:

  * duplicate      -> ``provider_merge.merge_providers`` retires each clone (soft
                      is_active=False + ``attributes.merged_into_slug`` so the
                      profile route 301s the old slug), gap-fills the primary,
                      repoints FKs, and records a ``DedupeResolution`` 'merged'.
  * multi_location -> stamp all members with a shared ``location_group_id`` (kept,
                      cross-linked as sibling locations) + record 'multi_location'.
  * parent_child   -> set each non-primary member's ``parent_provider_id`` to the
                      primary (kept, rendered as departments) + record 'parent_child'.

DRY-RUN by default (prints the plan). ``--apply`` writes and emits an undo CSV of
retired clones + link mutations so the change is reversible.

    .venv\\Scripts\\python.exe scripts\\dedupe_apply_2026_07_06.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\dedupe_apply_2026_07_06.py --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import DedupeResolution, Provider, dedupe_pair_key  # noqa: E402
from app.dedupe.cluster import ProviderRecord, cluster_providers  # noqa: E402

_UNDO_CSV = "dedupe_apply_undo_2026-07-06.csv"


def _load_records(db) -> list[ProviderRecord]:
    rows = db.execute(
        select(
            Provider.id, Provider.provider_name, Provider.address, Provider.phone,
            Provider.google_place_id, Provider.google_review_count, Provider.verified, Provider.slug,
        ).where(Provider.is_active.is_(True))
    ).all()
    return [
        ProviderRecord(
            id=str(r.id), name=r.provider_name or "", address=r.address, phone=r.phone,
            google_place_id=r.google_place_id, review_count=int(r.google_review_count or 0),
            verified=bool(r.verified), slug=r.slug,
        )
        for r in rows
    ]


def _record_resolution(db, id_a: str, id_b: str, resolution: str) -> None:
    key = dedupe_pair_key(id_a, id_b)
    existing = db.scalar(select(DedupeResolution).where(DedupeResolution.pair_key == key))
    if existing is not None:
        existing.resolution = resolution
        return
    lo, hi = sorted((id_a, id_b))
    db.add(DedupeResolution(pair_key=key, provider_id_a=lo, provider_id_b=hi, resolution=resolution))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the catalog dedupe proposal.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)
    dry = not args.apply

    undo_rows: list[dict] = []
    counts = {"retired": 0, "multi_linked": 0, "child_linked": 0, "skipped": 0, "clusters": 0}

    with SessionLocal() as db:
        clusters = cluster_providers(_load_records(db))
        counts["clusters"] = len(clusters)
        for c in clusters:
            primary = db.get(Provider, c.primary.id)
            if primary is None:
                counts["skipped"] += 1
                continue

            if c.relationship_type == "duplicate":
                for clone_rec in c.clones:
                    dup = db.get(Provider, clone_rec.id)
                    if dup is None or not dup.is_active:
                        continue
                    print(f"  RETIRE {dup.provider_name!r} -> {primary.provider_name!r}")
                    undo_rows.append({
                        "action": "retire", "id": dup.id, "keep_id": primary.id,
                        "provider_name": dup.provider_name, "old_is_active": dup.is_active,
                        "old_draft": dup.draft,
                    })
                    if not dry:
                        try:
                            merge_providers(db, keep_id=str(primary.id), dup_id=str(dup.id))
                            db.commit()
                            counts["retired"] += 1
                        except ValueError as e:  # operator-sourced / invalid -> skip
                            db.rollback()
                            counts["skipped"] += 1
                            print(f"    SKIP ({e})")
                    else:
                        counts["retired"] += 1

            elif c.relationship_type == "multi_location":
                members = [db.get(Provider, m.id) for m in c.members]
                members = [m for m in members if m is not None]
                group = next((m.location_group_id for m in members if m.location_group_id), None) or str(uuid4())
                for m in members:
                    print(f"  MULTI-LOC {m.provider_name!r} <- group")
                    undo_rows.append({
                        "action": "location_group_id", "id": m.id, "keep_id": "",
                        "provider_name": m.provider_name, "old_is_active": m.location_group_id or "",
                        "old_draft": "",
                    })
                    if not dry:
                        m.location_group_id = group
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        if not dry:
                            _record_resolution(db, str(members[i].id), str(members[j].id), "multi_location")
                    counts["multi_linked"] += 1 if not dry else 0
                if not dry:
                    db.commit()
                if dry:
                    counts["multi_linked"] += len(members)

            elif c.relationship_type == "parent_child":
                for child_rec in c.clones:
                    child = db.get(Provider, child_rec.id)
                    if child is None:
                        continue
                    if primary.parent_provider_id == child.id:  # cycle guard
                        counts["skipped"] += 1
                        continue
                    print(f"  CHILD {child.provider_name!r} -> parent {primary.provider_name!r}")
                    undo_rows.append({
                        "action": "parent_provider_id", "id": child.id, "keep_id": primary.id,
                        "provider_name": child.provider_name,
                        "old_is_active": child.parent_provider_id or "", "old_draft": "",
                    })
                    if not dry:
                        child.parent_provider_id = str(primary.id)
                        _record_resolution(db, str(primary.id), str(child.id), "parent_child")
                    counts["child_linked"] += 1
                if not dry:
                    db.commit()

    if not dry and undo_rows:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "action", "id", "keep_id", "provider_name", "old_is_active", "old_draft",
            ])
            w.writeheader()
            w.writerows(undo_rows)

    print(
        f"\nclusters={counts['clusters']}  retired={counts['retired']}  "
        f"multi_linked={counts['multi_linked']}  child_linked={counts['child_linked']}  "
        f"skipped={counts['skipped']}"
    )
    if dry:
        print("DRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
    else:
        print(f"APPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
