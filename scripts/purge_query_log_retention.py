"""Truncate raw ``query_log`` rows older than the retention window (P5, §2.3).

The query_log is already anonymized (no IP/UA/user-id), so this is hygiene, not
PII deletion: keep ~12 months of raw rows for the search-intelligence dashboard,
drop older ones. Intended to run on a schedule (monthly) once Casey wires a cron;
until then it is a manual, gated op.

DEFAULT IS DRY-RUN: prints the count it would delete and writes nothing. Deleting
is a prod-DB write, so ``--apply`` requires ``--confirm`` (the repo .env can point
DATABASE_URL at prod — every run prints the sanitized target).

    .venv\\Scripts\\python.exe scripts\\purge_query_log_retention.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\purge_query_log_retention.py --apply --confirm  # deletes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.v1.query_log import RETENTION_DAYS, purge_old_query_logs  # noqa: E402


def _sanitized_target() -> str:
    url = DATABASE_URL or ""
    if "@" in url:
        return "..." + url.split("@", 1)[1]
    return url or "(unset)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--apply", action="store_true", help="actually delete")
    parser.add_argument("--confirm", action="store_true", help="required with --apply")
    args = parser.parse_args()

    print(f"target: {_sanitized_target()}")
    print(f"retention: keep <= {args.days} days of raw query_log rows")

    with SessionLocal() as db:
        would = purge_old_query_logs(db, older_than_days=args.days, dry_run=True)
        print(f"rows older than {args.days} days: {would}")
        if not args.apply:
            print("DRY RUN — nothing deleted. Re-run with --apply --confirm to delete.")
            return 0
        if not args.confirm:
            print("REFUSING to delete without --confirm.")
            return 2
        deleted = purge_old_query_logs(db, older_than_days=args.days, dry_run=False)
        print(f"DELETED {deleted} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
