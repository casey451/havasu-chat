"""
Evaluate conditions cache and dispatch alert emails.

Usage:
  python -m scripts.evaluate_and_dispatch_alerts
  python -m scripts.evaluate_and_dispatch_alerts --dry-run
  python -m scripts.evaluate_and_dispatch_alerts --report
  python -m scripts.evaluate_and_dispatch_alerts --alert-type heat_advisory
  python -m scripts.evaluate_and_dispatch_alerts --user-id <uuid>

--report runs a read-only safety-rule audit: it evaluates every V1 rule
against the conditions cache and prints a structured report (fired / clear /
data_unavailable per rule, with per-source freshness). It writes NOTHING to
the database and dispatches NOTHING -- safe to run against any environment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.alerts.dispatcher import dispatch_alerts  # noqa: E402
from app.alerts.report import build_safety_report  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate and dispatch condition alerts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Read-only safety-rule audit; writes/sends nothing.",
    )
    parser.add_argument("--alert-type", dest="alert_type", default=None)
    parser.add_argument("--user-id", dest="user_id", default=None)
    args = parser.parse_args(argv)

    if args.report:
        with SessionLocal() as db:
            report = build_safety_report(db, alert_type_filter=args.alert_type)
        print(json.dumps(report.to_dict()))
        return 0

    with SessionLocal() as db:
        stats = dispatch_alerts(
            db,
            dry_run=args.dry_run,
            alert_type_filter=args.alert_type,
            user_id_filter=args.user_id,
        )

    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
