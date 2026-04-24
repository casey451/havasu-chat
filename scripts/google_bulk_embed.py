"""
Run: python scripts/google_bulk_embed.py [--batch-size N] [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.google_bulk_embed import run_embed
from app.db.database import SessionLocal


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Backfill Provider embeddings (Google bulk import)")
    p.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Query/OpenAI batch size (default: 50)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute text/counters only; do not call OpenAI or write rows",
    )
    args = p.parse_args()
    if args.batch_size < 1:
        print("error: --batch-size must be at least 1", file=sys.stderr)
        return 2

    try:
        with SessionLocal() as db:
            c = run_embed(db, batch_size=args.batch_size, dry_run=bool(args.dry_run))
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print("Google bulk embed complete")
    print(f"  batch_size:                      {args.batch_size}")
    print(f"  scanned:                         {c.scanned}")
    print(f"  embedded:                        {c.embedded}")
    print(f"  skipped_no_name:                 {c.skipped_no_name}")
    print(f"  skipped_only_name:               {c.skipped_only_name}")
    print(f"  errors:                          {c.errors}")
    if args.dry_run:
        print("  (dry run — no OpenAI, no database writes)")

    return 1 if c.errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
