"""Submit web-audited candidate businesses into the contribution review queue.

These are the ~90 businesses the 2026-06-15 coverage audit found missing from
the directory (category_coverage_candidates_2026-06-15.csv), gathered from the
open web (Yelp / Go Lake Havasu / business sites) — NOT the Google Places API.

Because the data is web-sourced and unverified, this loader does NOT insert live
providers. It funnels each candidate through the SAME path a visitor's "Suggest a
business" submission uses (``create_contribution``) so every row lands as a
*pending* contribution flagged ``unverified=True``. You then approve (and edit /
enrich) them from the admin review queue — nothing goes public unreviewed.

Idempotent-ish: a candidate whose URL already has a pending/approved contribution
is skipped (``has_pending_or_approved_duplicate_url``), so re-running won't pile
up duplicates.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\load_candidates_to_review_queue.py --dry-run
    .venv\\Scripts\\python.exe scripts\\load_candidates_to_review_queue.py            # submit
    .venv\\Scripts\\python.exe scripts\\load_candidates_to_review_queue.py --only marine-repair,marine-dealers,marine-supply,on-the-water
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pydantic import ValidationError  # noqa: E402

from app.db.contribution_store import (  # noqa: E402
    create_contribution,
    has_pending_or_approved_duplicate_url,
    normalize_submission_url,
)
from app.db.database import SessionLocal  # noqa: E402
from app.schemas.contribution import ContributionCreate  # noqa: E402

DEFAULT_CSV = _ROOT / "category_coverage_candidates_2026-06-15.csv"
LOAD_SOURCE = "operator_backfill"


def _note(address: str, phone: str, notes: str) -> str | None:
    parts = [p.strip() for p in (address, phone, notes) if p and p.strip()]
    return " · ".join(parts) or None


def run(*, csv_path: Path, only: set[str] | None, dry_run: bool = True) -> Counter:
    counts: Counter = Counter()
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    db = SessionLocal()
    try:
        for row in rows:
            sub = (row.get("subcategory") or "").strip()
            if only and sub not in only:
                continue
            name = (row.get("business") or "").strip()
            url = (row.get("source_url") or "").strip()
            if not name:
                continue
            if not url:
                counts["skip_no_url"] += 1
                print(f"  SKIP (no source URL): {name}")
                continue
            if has_pending_or_approved_duplicate_url(db, normalize_submission_url(url)):
                counts["skip_dup"] += 1
                print(f"  SKIP (URL already submitted/approved): {name}")
                continue
            try:
                body = ContributionCreate(
                    entity_type="provider",
                    submission_name=name,
                    submission_url=url,  # type: ignore[arg-type]
                    source_url=url,
                    submission_category_hint=sub or None,
                    submission_notes=_note(
                        row.get("address", ""), row.get("phone", ""), row.get("notes", "")
                    ),
                    source=LOAD_SOURCE,
                    unverified=True,
                )
            except ValidationError as exc:
                counts["skip_invalid"] += 1
                print(f"  SKIP (invalid: {exc.errors()[0].get('msg', 'bad value')}): {name}")
                continue

            counts["submit"] += 1
            print(f"  {'WOULD SUBMIT' if dry_run else 'SUBMITTED'} [{sub}]: {name}")
            if not dry_run:
                create_contribution(db, body, submitter_ip_hash="web_audit_2026-06-15")
    finally:
        db.close()

    verb = "would submit" if dry_run else "submitted"
    print(
        f"\n{verb} {counts['submit']} contributions | skipped: "
        f"dup {counts['skip_dup']}, no-url {counts['skip_no_url']}, invalid {counts['skip_invalid']}"
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="candidates CSV path")
    parser.add_argument(
        "--only", default="", help="comma-separated subcategories to limit to (e.g. marine-repair)"
    )
    args = parser.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    run(csv_path=args.csv, only=only, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
