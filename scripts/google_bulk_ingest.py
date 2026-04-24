"""
Run: python scripts/google_bulk_ingest.py <path-to-jsonl> [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.google_bulk_ingest import run_ingest
from app.db.database import SessionLocal


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Ingest Google enrichment JSONL into Provider rows")
    p.add_argument("jsonl_path", type=Path, help="Path to .jsonl file")
    p.add_argument("--dry-run", action="store_true", help="No database writes")
    args = p.parse_args()
    dry_run = bool(args.dry_run)
    path = args.jsonl_path
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        c = run_ingest(path, db, dry_run=dry_run)

    print("Google bulk ingest complete")
    print(f"  path:                            {path.resolve()}")
    print(f"  fetched_rows:                    {c.fetched_rows}")
    print(f"  inserted:                        {c.inserted}")
    print(f"  updated:                         {c.updated}")
    print(f"  skipped_missing_required:        {c.skipped_missing_required}")
    print(f"  skipped_duplicate_in_file:       {c.skipped_duplicate_in_file}")
    print(f"  errors:                          {c.errors}")
    if dry_run:
        print("  (dry run — no database writes)")

    return 1 if c.errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
