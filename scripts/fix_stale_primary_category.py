"""Fix stale ``Provider.primary_category`` left behind by the 2026-06-15 recats.

The companion audit (``scripts/audit_primary_subcategory_mismatch.py``) finds
active, non-draft providers whose ``primary_category`` disagrees with the
canonical primary for their ``subcategory`` and sorts them into three buckets.
This script applies the ONE safe correction —

    primary_category = primary_for_subcategory(subcategory)

— and by default ONLY to the ``stale_recat`` bucket (mismatches provably caused
by a cross-primary recat that set ``subcategory`` but not ``primary_category``).
It re-runs the audit's own classifier, so the two can never drift.

Safety rails (this writes to PRODUCTION — repo rule: dry-run -> show counts ->
Casey approves -> apply):

  * ``--dry-run`` is the DEFAULT. You must pass ``--apply`` to write.
  * Never nulls a primary: if ``primary_for_subcategory(subcategory)`` is
    ``None`` the row is skipped (those land in the audit's ``no_target`` bucket).
  * Idempotent: a row already at the expected primary is counted "already_ok".
  * ``--ids 1,2,3`` lets Casey green-light specific ``review``-bucket rows after
    eyeballing them; without it, only ``stale_recat`` rows are touched.

Usage (Windows / PowerShell)::

    .venv\\Scripts\\python.exe scripts\\fix_stale_primary_category.py --dry-run
    .venv\\Scripts\\python.exe scripts\\fix_stale_primary_category.py --apply
    .venv\\Scripts\\python.exe scripts\\fix_stale_primary_category.py --apply --ids 1234,5678
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from scripts.audit_primary_subcategory_mismatch import (  # noqa: E402
    DEFAULT_RECAT_CSV,
    classify,
    load_recat_rows,
)


def _parse_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for tok in raw.replace(",", " ").split():
        try:
            out.add(int(tok))
        except ValueError:
            print(f"  WARN: ignoring non-integer id {tok!r}")
    return out


def run(*, recat_csv: Path, apply: bool, extra_ids: set[int]) -> Counter:
    counts: Counter = Counter()
    recat_rows = load_recat_rows(recat_csv)

    db = SessionLocal()
    try:
        candidates = classify(db, recat_rows)

        # Targets = the provably-safe bucket, plus any ids Casey explicitly
        # green-lit from the review bucket. (no_target rows are never eligible —
        # expected_primary is None there.)
        eligible = [
            r
            for r in candidates
            if r.expected_primary is not None
            and (r.bucket == "stale_recat" or r.provider_id in extra_ids)
        ]
        # Surface any explicitly-named id that did NOT resolve to an eligible row.
        resolved_ids = {r.provider_id for r in eligible}
        for i in sorted(extra_ids - resolved_ids):
            counts["ids_not_eligible"] += 1
            print(f"  NOTE: --ids {i} is not a fixable mismatch (already ok, no_target, or unknown)")

        for r in sorted(eligible, key=lambda r: r.provider_name.lower()):
            provider = db.get(Provider, r.provider_id)
            if provider is None:
                counts["vanished"] += 1
                print(f"  SKIP (provider {r.provider_id} no longer present): {r.provider_name}")
                continue
            # Re-derive at apply time off the LIVE row (never trust stale audit).
            expected = r.expected_primary
            if provider.primary_category == expected:
                counts["already_ok"] += 1
                continue
            if expected is None:  # defensive: must never null a primary
                counts["skip_no_target"] += 1
                continue
            counts[r.bucket] += 1
            counts["changed"] += 1
            print(
                f"  {'WOULD SET' if not apply else 'SET'} [{provider.id}] {provider.provider_name}: "
                f"subcat={provider.subcategory} | primary "
                f"{provider.primary_category} -> {expected}  ({r.bucket})"
            )
            if apply:
                provider.primary_category = expected

        if apply:
            db.commit()
    finally:
        db.close()

    verb = "changed" if apply else "would change"
    print(
        f"\n{verb} {counts['changed']} "
        f"(stale_recat {counts['stale_recat']} + review-by-id {counts['review']}) | "
        f"already-ok {counts['already_ok']} | "
        f"ids-not-eligible {counts['ids_not_eligible']}"
    )
    if not apply:
        print("DRY RUN — no rows written. Re-run with --apply (after approval) to commit.")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write to the DB (default is a dry run)"
    )
    parser.add_argument("--dry-run", action="store_true", help="explicit no-op dry run (default)")
    parser.add_argument(
        "--ids", type=str, default="", help="comma/space-separated provider ids from the review bucket to also fix"
    )
    parser.add_argument("--recat-csv", type=Path, default=DEFAULT_RECAT_CSV)
    args = parser.parse_args()
    run(recat_csv=args.recat_csv, apply=args.apply, extra_ids=_parse_ids(args.ids))


if __name__ == "__main__":
    main()
