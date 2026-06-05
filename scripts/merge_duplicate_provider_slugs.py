"""P1.10 — merge duplicate provider rows (re-scrapes of the SAME physical place).

Groups ACTIVE providers by normalized name, then merges within a group only when
the members are confidently the same physical place. Two safety gates, learned
the hard way (a name-only version would have collapsed distinct chain locations):

  1. PLACE_ID gate — a name group with 2+ distinct Google ``google_place_id``s is
     a multi-location chain (e.g. several Chevron / Circle K / Starbucks stations
     share a name); it is SKIPPED and listed, never merged.
  2. ADDRESS gate — within a single-place_id group, a duplicate that has NO
     place_id of its own only merges if its street number matches the survivor's.
     This catches a chain's *second* location that simply lacks a place_id (e.g.
     "Donut Post South" at 2837 Maricopa vs Donut Post at 1730 W Acoma; the
     Showplace Ave McDonald's vs the Swanson Ave one) — those are HELD, not merged.

Survivor per group: verified > has place_id > has entity location > oldest. Then:
  DRY-RUN (default): prints the merge plan + counts. NO writes.
  --apply:           deactivates each duplicate and stamps
                     ``attributes.merged_into_slug = <survivor slug>`` so the
                     provider route 301s old slugs to the survivor.

Always read the dry-run: the ``[no place_id — address matches]`` merges are the
least-certain ones; eyeball them before --apply.

Run order per CLAUDE.md: --dry-run -> show Casey the counts -> Casey approves
-> --apply. Never run --apply without that approval.

Usage:
    python scripts/merge_duplicate_provider_slugs.py            # dry run
    python scripts/merge_duplicate_provider_slugs.py --apply    # after approval
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.provider_name import _norm_provider_name, clean_name  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Location, Provider  # noqa: E402

# Confirmed multi-location businesses whose second location lacks a place_id, so
# the place_id gate alone wouldn't catch them. Belt-and-suspenders with the
# address gate below. Normalized names.
_MANUAL_SKIP = {"mcdonald's", "donut post"}


def _survivor_sort_key(p: Provider) -> tuple:
    return (
        not bool(p.verified),                 # verified first
        p.google_place_id is None,            # has a premise next
        getattr(p, "entity_id", None) is None,
        p.created_at or 0,                    # oldest wins ties
    )


def _distinct_place_ids(members: list[Provider]) -> set[str]:
    pids = {(m.google_place_id or "").strip() for m in members}
    pids.discard("")
    return pids


def _address(db, p: Provider) -> str | None:
    if p.entity_id:
        loc = db.query(Location).filter(Location.entity_id == p.entity_id).first()
        if loc and loc.address:
            return loc.address
    return p.address


def _street_num(addr: str | None) -> str | None:
    """Leftmost multi-digit token — the street number for a US address string."""
    if not addr:
        return None
    m = re.search(r"\d{1,6}", addr)
    return m.group(0) if m else None


def _address_corroborates(dup_addr: str | None, surv_addr: str | None) -> bool:
    a, b = _street_num(dup_addr), _street_num(surv_addr)
    return bool(a and b and a == b)  # missing numbers -> not corroborated (hold)


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
        chain_groups: list[tuple[str, int]] = []
        manual_held: list[str] = []
        for name, members in groups.items():
            if len(members) < 2 or not name:
                continue
            if name in _MANUAL_SKIP:
                manual_held.append(name)
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
        if manual_held:
            print(f"held (known multi-location):     {sorted(manual_held)}")

        merged = 0
        addr_held: list[str] = []
        for name, members in sorted(merge_groups):
            members.sort(key=_survivor_sort_key)
            survivor, *dups = members
            surv_pid = (survivor.google_place_id or "").strip()
            surv_addr = _address(db, survivor)
            print(f"\n[{name}]")
            print(
                f"  KEEP  {survivor.slug}  (verified={survivor.verified}, "
                f"place_id={'yes' if surv_pid else 'no'})"
            )
            for d in dups:
                d_pid = (d.google_place_id or "").strip()
                if d_pid:
                    do_merge, tag = True, ""  # shares the group's place_id
                else:
                    d_addr = _address(db, d)
                    if _address_corroborates(d_addr, surv_addr):
                        do_merge, tag = True, "   [no place_id — address matches]"
                    else:
                        do_merge = False
                        addr_held.append(name)
                        print(
                            f"  HOLD  {d.slug}  [no place_id + address differs — "
                            f"possible 2nd location: {d_addr!r} vs {surv_addr!r}]"
                        )
                if not do_merge:
                    continue
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
        if addr_held:
            print(f"held by address gate (verify manually): {sorted(set(addr_held))}")
        if args.apply:
            db.commit()
            print("APPLIED.")
        else:
            print("DRY RUN — nothing written. Re-run with --apply after Casey approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
