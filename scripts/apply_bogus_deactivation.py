"""Apply (reversible) soft-deactivation for bogus listings — DRY-RUN BY DEFAULT.

Companion to ``scripts/audit_bogus_listings.py``. Reads that audit's flagged CSV,
takes only the rows whose ``recommended_action`` is ``deactivate (is_active=
False)``, re-checks each against live DB state, and — only when ``--apply`` is
passed — flips ``is_active`` to False inside one transaction. It writes an undo
CSV of exactly the ids it changed so the action is fully reversible via
``--reactivate-from``.

This honors the repo protocol: dry-run -> show counts -> Casey approves ->
apply. Running it with no flags writes NOTHING.

Safety re-checks at apply time (belt-and-suspenders; a row can change between
audit and apply):
  * skip rows that are already inactive / draft (no-op)
  * skip rows that became verified, claimed, or sponsored since the audit
  * only soft-deactivation (is_active=False); never deletes

Usage:
    # 1. dry run — see exactly what would change, change nothing:
    railway run python scripts/apply_bogus_deactivation.py --from flagged_prod.csv

    # 2. apply (writes is_active=False; emits undo CSV):
    railway run python scripts/apply_bogus_deactivation.py --from flagged_prod.csv \
        --apply --undo-csv undo_deactivation.csv

    # 3. reverse it if needed:
    railway run python scripts/apply_bogus_deactivation.py \
        --reactivate-from undo_deactivation.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Claim, Provider  # noqa: E402

_DEACTIVATE = "deactivate"


def _is_sponsored(p: Provider, now: datetime) -> bool:
    tier = (p.tier or "").strip()
    if tier not in ("", "free"):
        return True
    su = p.sponsored_until
    if su is not None:
        if su.tzinfo is None:
            su = su.replace(tzinfo=UTC)
        if su > now:
            return True
    return False


def _read_ids(path: str, *, only_deactivate: bool) -> list[tuple[str, str]]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if only_deactivate:
                action = (r.get("recommended_action") or "")
                if not action.startswith(_DEACTIVATE):
                    continue
            pid = r.get("id")
            if pid:
                rows.append((pid, r.get("name", "")))
    return rows


def deactivate(from_csv: str, apply: bool, undo_csv: str | None) -> int:
    db = SessionLocal()
    now = datetime.now(UTC)
    try:
        wanted = _read_ids(from_csv, only_deactivate=True)
        claimed = {
            row[0]
            for row in db.query(Claim.entity_id).filter(Claim.status == "verified").all()
        }
        to_change, skipped = [], []
        for pid, name in wanted:
            p = db.get(Provider, pid)
            if p is None:
                skipped.append((pid, name, "not-found"))
                continue
            if not p.is_active or p.draft:
                skipped.append((pid, name, "already-hidden"))
                continue
            if p.verified or p.entity_id in claimed or _is_sponsored(p, now):
                skipped.append((pid, name, "now-protected"))
                continue
            to_change.append(p)

        print("=" * 64)
        print("SOFT-DEACTIVATION", "(APPLY)" if apply else "(DRY RUN — no writes)")
        print("=" * 64)
        print(f"candidates in CSV (deactivate): {len(wanted)}")
        print(f"will deactivate:                {len(to_change)}")
        print(f"skipped:                        {len(skipped)}")
        from collections import Counter
        for reason, n in Counter(s[2] for s in skipped).most_common():
            print(f"    {n:5d}  {reason}")
        print()
        for p in to_change[:25]:
            print(f"    - {p.provider_name[:50]} ({p.id})")
        if len(to_change) > 25:
            print(f"    ... and {len(to_change) - 25} more")

        if not apply:
            print("\nDRY RUN: nothing written. Re-run with --apply to deactivate.")
            return 0

        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["id", "name"])
                for p in to_change:
                    w.writerow([p.id, p.provider_name])

        for p in to_change:
            p.is_active = False
        db.commit()
        print(f"\nAPPLIED: {len(to_change)} rows set is_active=False.")
        if undo_csv:
            print(f"Undo list written to {undo_csv} "
                  f"(reverse with --reactivate-from {undo_csv} --apply).")
        return 0
    finally:
        db.close()


def reactivate(undo_csv: str, apply: bool) -> int:
    db = SessionLocal()
    try:
        ids = _read_ids(undo_csv, only_deactivate=False)
        changed = 0
        for pid, _name in ids:
            p = db.get(Provider, pid)
            if p is not None and not p.is_active:
                if apply:
                    p.is_active = True
                changed += 1
        if apply:
            db.commit()
        verb = "REACTIVATED" if apply else "would reactivate"
        print(f"{verb}: {changed} rows (is_active=True).")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reversible soft-deactivation (dry-run default).")
    ap.add_argument("--from", dest="from_csv", help="flagged CSV from audit_bogus_listings.py")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo CSV to reverse a prior apply")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-csv", default="undo_deactivation.csv", help="where to write the undo list")
    args = ap.parse_args(argv)

    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    if args.from_csv:
        return deactivate(args.from_csv, args.apply, args.undo_csv)
    ap.error("pass --from <flagged.csv> or --reactivate-from <undo.csv>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
