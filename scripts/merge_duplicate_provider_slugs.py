"""P1.10 — merge duplicate provider rows (ZENSHI x2 etc.) — CASEY-GATED data op.

Finds groups of ACTIVE providers whose normalized display name collides
(via the canonical ``_norm_provider_name``), picks a survivor per group
(verified > has google_place_id > has entity location > oldest), and:

  DRY-RUN (default): prints the merge plan + counts. NO writes.
  --apply:           deactivates each duplicate and stamps
                     ``attributes.merged_into_slug = <survivor slug>`` so the
                     provider route 301s old slugs to the survivor.

Run order per CLAUDE.md: --dry-run -> show Casey the counts -> Casey approves
-> --apply. Never run --apply without that approval.

Usage:
    python scripts/merge_duplicate_provider_slugs.py            # dry run
    python scripts/merge_duplicate_provider_slugs.py --apply    # after approval
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.provider_name import _norm_provider_name, clean_name  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def _survivor_sort_key(p: Provider) -> tuple:
    return (
        not bool(p.verified),                 # verified first
        p.google_place_id is None,            # has a premise next
        getattr(p, "entity_id", None) is None,
        p.created_at or 0,                    # oldest wins ties
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (Casey-approved only)")
    args = ap.parse_args()

    with SessionLocal() as db:
        rows = (
            db.query(Provider)
            .filter(Provider.is_active.is_(True), Provider.slug.isnot(None))
            .all()
        )
        groups: dict[str, list[Provider]] = defaultdict(list)
        for p in rows:
            groups[_norm_provider_name(clean_name(p.provider_name or ""))].append(p)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1 and k}
        print(f"active providers scanned: {len(rows)}")
        print(f"duplicate-name groups:    {len(dup_groups)}")
        merged = 0
        for key, members in sorted(dup_groups.items()):
            members.sort(key=_survivor_sort_key)
            survivor, *dups = members
            print(f"\n[{key}]")
            print(f"  KEEP  {survivor.slug}  (verified={survivor.verified}, "
                  f"place_id={'yes' if survivor.google_place_id else 'no'})")
            for d in dups:
                print(f"  MERGE {d.slug} -> {survivor.slug}")
                merged += 1
                if args.apply:
                    d.is_active = False
                    attrs = dict(d.attributes or {})
                    attrs["merged_into_slug"] = survivor.slug
                    d.attributes = attrs
                    db.add(d)
        print(f"\nrows that would be merged: {merged}")
        if args.apply:
            db.commit()
            print("APPLIED.")
        else:
            print("DRY RUN — nothing written. Re-run with --apply after Casey approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
