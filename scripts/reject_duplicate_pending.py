"""Reject pending web-audit provider contributions that duplicate an existing
active provider by name.

These are rows the dedup guard skipped at approval time — the 2026-06-15 audit
flagged them "missing" but they already exist in the directory — left sitting
pending. This cleans them out of the review queue as ``rejected``/``duplicate``.

Scope: ``status=pending`` + ``source=operator_backfill`` + ``entity_type=provider``
whose normalized ``submission_name`` matches an active provider. Nothing else is
touched.

Usage (Windows / PowerShell):
    .venv\\Scripts\\python.exe scripts\\reject_duplicate_pending.py --dry-run
    .venv\\Scripts\\python.exe scripts\\reject_duplicate_pending.py            # reject
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.contribution_store import update_contribution_status  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Provider  # noqa: E402


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def run(*, dry_run: bool = True) -> Counter:
    counts: Counter = Counter()
    db = SessionLocal()
    try:
        active_names = {
            _norm(n)
            for (n,) in db.query(Provider.provider_name).filter(Provider.is_active.is_(True)).all()
        }
        rows = (
            db.query(Contribution)
            .filter(
                Contribution.status == "pending",
                Contribution.source == "operator_backfill",
                Contribution.entity_type == "provider",
            )
            .order_by(Contribution.submission_name)
            .all()
        )
        for c in rows:
            if _norm(c.submission_name) not in active_names:
                continue
            counts["reject"] += 1
            print(
                f"  {'WOULD REJECT' if dry_run else 'REJECTED'} dup: #{c.id} "
                f"[{c.submission_category_hint}] {c.submission_name}"
            )
            if not dry_run:
                update_contribution_status(
                    db,
                    c.id,
                    "rejected",
                    review_notes="Business already exists as an active provider (audit mis-flagged as missing). 2026-06-16.",
                    rejection_reason="duplicate",
                )
    finally:
        db.close()
    print(f"\n{'would reject' if dry_run else 'rejected'} {counts['reject']} duplicate pending contributions")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
