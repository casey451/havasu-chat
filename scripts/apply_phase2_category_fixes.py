"""Apply the Phase-2 curated category fixes (2026-06-16 mismatch triage, Buckets 1+2).

Follow-up to the 2026-06-15 coverage audit. The read-only mismatch audit found
active providers where ``primary_category != primary_for_subcategory(subcategory)``.
``CATEGORY_MISMATCH_TRIAGE_2026-06-16.md`` sorts them into buckets; this applies
the two non-judgment buckets from a curated CSV
(``category_recat_phase2_2026-06-16.csv``):

  * **Bucket 1** — the primary is correct; the SUBCATEGORY is the wrong/generic
    signal. We set ``subcategory`` to a leaf whose canonical primary equals the
    (already-correct) primary, so the mismatch self-resolves and the row also
    surfaces on the right ``/lake-havasu/{sub}`` landing. ``primary`` is untouched.
  * **Bucket 2** — the primary is the stale one. We set ``primary_category``
    (and, for the golf courses, the ``subcategory`` leaf too).

Bucket 3 (genuine domain calls — auto/marine cross-trade, realtor-vs-VR-manager,
nurseries, etc.) is OUT OF SCOPE and left untouched.

Safety (CLAUDE.md prod-data rule): DRY-RUN BY DEFAULT. Writing needs BOTH
``--apply`` and ``--confirm``. Matching is conservative — exact, case/whitespace-
insensitive ``provider_name`` against an active, non-draft provider; zero or
multiple matches are reported and skipped (never guessed). Each write is checked
to actually resolve the mismatch (``primary == primary_for_subcategory(subcat)``);
a row that wouldn't is reported and skipped. On apply, the prior
(subcategory, primary) of every changed row is written to an undo CSV.

Usage (Windows / PowerShell)::

    .venv\\Scripts\\python.exe scripts\\apply_phase2_category_fixes.py                      # dry-run
    .venv\\Scripts\\python.exe scripts\\apply_phase2_category_fixes.py --apply --confirm     # write
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Make the report UTF-8 safe on a default Windows (cp1252) console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from sqlalchemy import func  # noqa: E402

from app.categories.subcategories import (  # noqa: E402
    SUBCATEGORY_TO_PRIMARY,
    primary_for_subcategory,
    subcategory_by_slug,
)
from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import Provider  # noqa: E402

DEFAULT_CSV = _ROOT / "category_recat_phase2_2026-06-16.csv"
_VALID_PRIMARIES = set(SUBCATEGORY_TO_PRIMARY.values())


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def _sanitized_target() -> str:
    url = engine.url
    return f"{url.drivername} db={url.database!r} host={url.host!r}"


def run(*, csv_path: Path, apply: bool = False, confirm: bool = False) -> Counter:
    counts: Counter = Counter()
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    undo: list[dict] = []
    db = SessionLocal()
    try:
        for row in rows:
            name = (row.get("business") or "").strip()
            set_sub = (row.get("set_subcategory") or "").strip() or None
            set_pri = (row.get("set_primary") or "").strip() or None
            bucket = (row.get("bucket") or "").strip()
            if not name:
                continue
            if set_sub is None and set_pri is None:
                counts["skip_no_change"] += 1
                continue
            if set_sub is not None and subcategory_by_slug(set_sub) is None:
                counts["skip_bad_target"] += 1
                print(f"  SKIP (unknown subcategory {set_sub!r}): {name}")
                continue
            if set_pri is not None and set_pri not in _VALID_PRIMARIES:
                counts["skip_bad_target"] += 1
                print(f"  SKIP (unknown primary {set_pri!r}): {name}")
                continue

            matches = (
                db.query(Provider)
                .filter(
                    func.lower(Provider.provider_name) == _norm(name),
                    Provider.is_active.is_(True),
                    Provider.draft.is_(False),
                )
                .all()
            )
            if not matches:
                counts["unmatched"] += 1
                print(f"  UNMATCHED (no active provider named): {name}")
                continue
            if len(matches) > 1:
                counts["ambiguous"] += 1
                print(f"  AMBIGUOUS ({len(matches)} matches, skipped): {name}")
                continue

            p = matches[0]
            new_sub = set_sub if set_sub is not None else p.subcategory
            new_pri = set_pri if set_pri is not None else p.primary_category

            # Guardrail: the resulting state must actually resolve the mismatch.
            if primary_for_subcategory(new_sub) != new_pri:
                counts["skip_would_not_resolve"] += 1
                print(
                    f"  SKIP (change wouldn't resolve mismatch): {name} -> "
                    f"sub={new_sub} primary={new_pri} "
                    f"(primary_for_subcategory={primary_for_subcategory(new_sub)})"
                )
                continue

            if p.subcategory == new_sub and p.primary_category == new_pri:
                counts["already_ok"] += 1
                continue

            counts["changed"] += 1
            counts[f"bucket_{bucket}"] += 1
            print(
                f"  {'WOULD FIX' if not apply else 'FIXED'} [{bucket}] {p.provider_name}: "
                f"sub {p.subcategory!r}->{new_sub!r} | primary {p.primary_category!r}->{new_pri!r}"
            )
            if apply:
                undo.append(
                    {
                        "provider_id": p.id,
                        "provider_name": p.provider_name,
                        "old_subcategory": p.subcategory or "",
                        "old_primary_category": p.primary_category or "",
                        "new_subcategory": new_sub or "",
                        "new_primary_category": new_pri or "",
                    }
                )
                p.subcategory = new_sub
                p.primary_category = new_pri
                db.add(p)

        if not apply:
            print(f"\nDRY RUN against {_sanitized_target()} — no rows written.")
            print("Re-run with --apply --confirm to write.")
        elif not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            db.rollback()
        else:
            undo_path = _ROOT / f"undo_phase2_category_fixes_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
            with undo_path.open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "provider_id",
                        "provider_name",
                        "old_subcategory",
                        "old_primary_category",
                        "new_subcategory",
                        "new_primary_category",
                    ],
                )
                w.writeheader()
                w.writerows(undo)
            db.commit()
            print(f"\nAPPLIED to {_sanitized_target()}. Undo CSV: {undo_path}")
    finally:
        db.close()

    verb = "fixed" if (apply and confirm) else "would fix"
    print(
        f"\n{verb} {counts['changed']} "
        f"(bucket1a {counts['bucket_1a']} 1b {counts['bucket_1b']} 1c {counts['bucket_1c']} "
        f"1d {counts['bucket_1d']} 1e {counts['bucket_1e']} | bucket2 {counts['bucket_2']}) | "
        f"already-ok {counts['already_ok']} | unmatched {counts['unmatched']} | "
        f"ambiguous {counts['ambiguous']} | "
        f"skipped(bad-target {counts['skip_bad_target']}, wouldnt-resolve {counts['skip_would_not_resolve']})"
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--confirm", action="store_true", help="required alongside --apply")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="curated fix CSV path")
    args = parser.parse_args()
    run(csv_path=args.csv, apply=args.apply, confirm=args.confirm)


if __name__ == "__main__":
    main()
