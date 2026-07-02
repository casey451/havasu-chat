"""Remediate the duplicate providers created by the marine + high add batches.

Those batches ran before the dedup guard, so each minted a *second* live provider
for a business that already existed. This finds those dup pairs at runtime
(my approved ``operator_backfill`` provider contributions whose created provider
shares a normalized name with another active provider) and, per pair:

  * PRIOR is draft (invisible): KEEP my live record, leave PRIOR — there is no
    visible duplicate. (Grand Island Disc Golf.)
  * else: DEACTIVATE my duplicate (is_active=False) + mark its contribution
    rejected/duplicate, then RECONCILE the surviving PRIOR so the business still
    lands on the right page:
      - PRIOR already in the audit's target subcategory  -> fix a stale primary only.
      - PRIOR mis-filed vs the audit's target            -> recat it to the target
        leaf (+ matching primary), EXCEPT names in _KEEP_PRIOR_SUBCAT where the
        existing categorization is as-good-or-better than the audit's.

Idempotent-ish: once my dup is deactivated it no longer counts as an active
same-name sibling, so a re-run finds nothing.

Usage (Windows / PowerShell):
    .venv\\Scripts\\python.exe scripts\\fix_add_duplicates.py --dry-run
    .venv\\Scripts\\python.exe scripts\\fix_add_duplicates.py            # apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.subcategories import primary_for_subcategory  # noqa: E402
from app.db.contribution_store import update_contribution_status  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Provider  # noqa: E402

# Dup names where the PRIOR record's existing subcategory is as-good-or-better than
# the audit's target, so we keep PRIOR's categorization and only drop my dup:
#   - a boat-tour company is fine as on-the-water (audit said attractions)
#   - West Marine is a marine retailer; marine-supply beats the audit's specialty
_KEEP_PRIOR_SUBCAT = {"sunset charter & tour co.", "west marine"}


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def run(*, dry_run: bool = True) -> Counter:
    counts: Counter = Counter()
    db = SessionLocal()
    try:
        active = db.query(Provider).filter(Provider.is_active.is_(True)).all()
        by_name: dict[str, list[Provider]] = {}
        for p in active:
            by_name.setdefault(_norm(p.provider_name), []).append(p)

        contribs = (
            db.query(Contribution)
            .filter(
                Contribution.source == "operator_backfill",
                Contribution.entity_type == "provider",
                Contribution.status == "approved",
                Contribution.created_provider_id.isnot(None),
            )
            .order_by(Contribution.submission_name)
            .all()
        )

        for c in contribs:
            mine = db.get(Provider, c.created_provider_id)
            if mine is None:
                continue
            priors = [p for p in by_name.get(_norm(c.submission_name), []) if p.id != mine.id]
            if not priors:
                continue  # not a duplicate
            if len(priors) > 1:
                counts["manual"] += 1
                print(f"  MANUAL ({len(priors)} priors, skipped): {c.submission_name}")
                continue
            prior = priors[0]
            target_sub = (c.submission_category_hint or "").strip()
            target_primary = primary_for_subcategory(target_sub)

            if prior.draft:
                counts["keep_mine"] += 1
                print(
                    f"  KEEP MINE (PRIOR is draft/invisible): {c.submission_name} "
                    f"[mine={mine.subcategory}]"
                )
                continue

            # Deactivate my duplicate + reject its contribution.
            counts["deactivate"] += 1
            print(f"  {'WOULD DEACTIVATE' if dry_run else 'DEACTIVATED'} dup: {c.submission_name} "
                  f"(mine {mine.id[:8]}, contrib #{c.id})")
            if not dry_run:
                mine.is_active = False
                db.add(mine)
                db.flush()
                update_contribution_status(
                    db,
                    c.id,
                    "rejected",
                    review_notes=(
                        f"Duplicate of existing provider {prior.id[:8]} "
                        f"({prior.provider_name!r}); add-created dup deactivated 2026-06-16."
                    ),
                    rejection_reason="duplicate",
                )

            # Reconcile the surviving PRIOR.
            if _norm(c.submission_name) in _KEEP_PRIOR_SUBCAT:
                counts["prior_left"] += 1
                print(f"       PRIOR left as-is: {prior.subcategory}/{prior.primary_category}")
            elif prior.subcategory == target_sub:
                expected = primary_for_subcategory(prior.subcategory)
                if expected and prior.primary_category != expected:
                    counts["prior_primary_fix"] += 1
                    print(f"       {'WOULD FIX' if dry_run else 'FIXED'} PRIOR primary: "
                          f"{prior.primary_category} -> {expected}")
                    if not dry_run:
                        prior.primary_category = expected
                        db.add(prior)
                else:
                    counts["prior_left"] += 1
                    print(f"       PRIOR already correct: {prior.subcategory}/{prior.primary_category}")
            else:
                counts["prior_recat"] += 1
                print(f"       {'WOULD RECAT' if dry_run else 'RECAT'} PRIOR: "
                      f"{prior.subcategory}/{prior.primary_category} -> {target_sub}/{target_primary}")
                if not dry_run:
                    prior.subcategory = target_sub
                    prior.primary_category = target_primary
                    db.add(prior)

            if not dry_run:
                db.commit()
    finally:
        db.close()

    print(
        f"\n{'(dry-run) ' if dry_run else ''}dups: deactivate {counts['deactivate']} | "
        f"keep-mine(draft prior) {counts['keep_mine']} | PRIOR recat {counts['prior_recat']} | "
        f"PRIOR primary-fix {counts['prior_primary_fix']} | PRIOR left {counts['prior_left']} | "
        f"manual {counts['manual']}"
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
