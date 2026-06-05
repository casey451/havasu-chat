"""P1.10 — merge duplicate provider rows (re-scrapes of the SAME physical place).

Groups ACTIVE providers by normalized name, then merges a group ONLY when its
members point at a single physical place — i.e. they carry **at most one distinct
Google ``google_place_id``**. This:

  * merges genuine re-scrapes (same business, e.g. ZENSHI x2 — one copy has the
    place_id, the older copy has none), and
  * never merges multi-location chains: multiple Chevron / Circle K / Starbucks
    stations share a name but have *different* place_ids, so those name groups are
    SKIPPED (and listed) rather than collapsed.

Name groups whose members carry 2+ distinct place_ids are reported as skipped
"chains". Groups with no place_id at all are ambiguous and skipped silently.

Survivor per group: verified > has entity location > oldest. Then:
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


# Normalized names held back for manual review even when they pass the
# single-place_id test — a chain whose no-place_id "-2" might be a second,
# un-geocoded location rather than a re-scrape. Excluded until confirmed.
_MANUAL_SKIP = {"mcdonald's"}


def _distinct_place_ids(members: list[Provider]) -> set[str]:
    pids = {(m.google_place_id or "").strip() for m in members}
    pids.discard("")
    return pids


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

        merge_groups: list[tuple[str, list[Provider]]] = []
        chain_groups: list[tuple[str, int]] = []  # (name, distinct place_id count)
        held = []
        for name, members in groups.items():
            if len(members) < 2 or not name:
                continue
            if name in _MANUAL_SKIP:
                held.append(name)
                continue
            n_pids = len(_distinct_place_ids(members))
            if n_pids == 1:
                merge_groups.append((name, members))
            elif n_pids >= 2:
                chain_groups.append((name, n_pids))
            # n_pids == 0 (no place_id anywhere): ambiguous — skip silently.

        print(f"active providers scanned:        {len(rows)}")
        print(f"true-duplicate groups (1 place): {len(merge_groups)}")
        print(f"skipped multi-location 'chains': {len(chain_groups)}")
        if held:
            print(f"held for manual review:          {sorted(held)}")

        merged = 0
        for name, members in sorted(merge_groups):
            members.sort(key=_survivor_sort_key)
            survivor, *dups = members
            print(f"\n[{name}]")
            print(
                f"  KEEP  {survivor.slug}  (verified={survivor.verified}, "
                f"place_id={'yes' if survivor.google_place_id else 'no'})"
            )
            for d in dups:
                # Flag the slightly-less-certain merges: a duplicate with no
                # place_id of its own, matched into the survivor only by name.
                tag = "" if d.google_place_id else "   [no place_id — name match only]"
                print(f"  MERGE {d.slug} -> {survivor.slug}{tag}")
                merged += 1
                if args.apply:
                    d.is_active = False
                    attrs = dict(d.attributes or {})
                    attrs["merged_into_slug"] = survivor.slug
                    d.attributes = attrs
                    db.add(d)

        if chain_groups:
            print("\nskipped — multiple distinct place_ids (= distinct locations, NOT merged):")
            for name, n in sorted(chain_groups):
                print(f"  SKIP  [{name}]  ({n} locations)")

        print(f"\nrows that would be merged: {merged}")
        if args.apply:
            db.commit()
            print("APPLIED.")
        else:
            print("DRY RUN — nothing written. Re-run with --apply after Casey approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
