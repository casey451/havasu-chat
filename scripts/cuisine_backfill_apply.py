"""WS9a cuisine backfill — GATED apply of operator-approved cuisines.

Writes ``Provider.attributes['cuisine'] = <slug>`` (a curated override that WINS
over the Google-types derivation — see
``app.categories.subcategories.effective_cuisine``) for the rows in an approved
proposals CSV, and flags each ``Provider.pending_review = True`` so it surfaces in
the review queue for a second look. Emits an undo CSV (slug, prev_cuisine) for a
one-command rollback.

Gate: dry-run by DEFAULT. Nothing is written unless ``--apply`` is passed AND the
run is a deliberate dispatch (this is the ``dry-run → Casey approves → apply``
prod-data gate; the approved CSV is the record of that approval). Idempotent: a
row whose curated cuisine already equals the proposal is skipped, so a re-run
writes 0. Only known enum slugs are accepted; an unknown slug aborts the row.

Like the dedupe apply, this runs in CI (cuisine-backfill-apply.yml) because the
repo .env points DATABASE_URL at Railway's internal host.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.categories.subcategories import cuisine_label  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_APPROVED_CSV = "docs/audits/2026-07/cuisine_apply_approved_2026-07-08.csv"
_UNDO_CSV = "cuisine_backfill_apply_undo_2026-07-08.csv"


def _load_approved(path: Path) -> list[tuple[str, str]]:
    """``[(slug, cuisine)]`` from the approved CSV; skips unknown-enum rows."""
    out: list[tuple[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = (row.get("slug") or "").strip()
            cuisine = (row.get("cuisine") or "").strip().lower()
            if not slug or not cuisine:
                continue
            if cuisine_label(cuisine) is None:
                print(f"  SKIP {slug}: '{cuisine}' is not a known cuisine enum slug")
                continue
            out.append((slug, cuisine))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply approved cuisine backfill.")
    parser.add_argument("--apply", action="store_true", help="Write to prod (else dry-run).")
    parser.add_argument("--csv", default=_APPROVED_CSV, help="Approved proposals CSV.")
    args = parser.parse_args(argv)

    approved = _load_approved(Path(args.csv))
    print(f"approved rows: {len(approved)}  (mode: {'APPLY' if args.apply else 'DRY-RUN'})")

    written = skipped_same = missing = 0
    undo_rows: list[tuple[str, str]] = []
    with SessionLocal() as db:
        for slug, cuisine in approved:
            p = (
                db.query(Provider)
                .filter(Provider.slug == slug, Provider.is_active.is_(True))
                .one_or_none()
            )
            if p is None:
                print(f"  MISS  {slug}: no active provider")
                missing += 1
                continue
            attrs = dict(p.attributes or {})
            prev = str(attrs.get("cuisine") or "")
            if prev == cuisine:
                skipped_same += 1
                continue
            undo_rows.append((slug, prev))
            print(f"  {'WRITE' if args.apply else 'would write'} {slug}: '{prev or '-'}' -> {cuisine}")
            if args.apply:
                attrs["cuisine"] = cuisine
                p.attributes = attrs
                p.pending_review = True
                written += 1
        if args.apply:
            db.commit()

    if undo_rows:
        with Path(_UNDO_CSV).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["slug", "cuisine"])  # prev value; blank clears the key
            w.writerows(undo_rows)
        print(f"undo CSV written: {_UNDO_CSV}")

    print(f"\nwrote: {written} | already-correct: {skipped_same} | missing: {missing}")
    if not args.apply:
        print("DRY RUN — no writes. Re-run with --apply after Casey's approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
