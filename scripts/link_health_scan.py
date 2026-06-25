"""CLI: scan the directory's stored outbound links and report broken ones.

Read-only and dry-run by design -- it issues outbound HTTP HEAD/GET and writes
nothing. Prints a category breakdown plus the actionable (broken / unreachable)
links so they can be reviewed before any persistence/admin-queue is wired up.

  python scripts/link_health_scan.py                  # full polite scan + report
  python scripts/link_health_scan.py --limit 200       # quick sample
  python scripts/link_health_scan.py --kind provider_website
  python scripts/link_health_scan.py --json > report.json

On the VPS it yields to the scrape/backup jobs (``--respect-jobs``): while the
vision scraper or nightly backup is running it pauses and re-checks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.monitoring import link_health as lh  # noqa: E402

# Units the scan should yield to on the VPS.
HEAVY_UNITS = ("havasu-vision-scrape.service", "havasu-db-backup.service")


def _heavy_job_running() -> bool:
    for unit in HEAVY_UNITS:
        try:
            rc = subprocess.run(
                ["systemctl", "is-active", "--quiet", unit], timeout=10
            ).returncode
        except Exception:
            rc = 3  # systemctl absent (e.g. dev/Windows) -> treat as not running
        if rc == 0:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None, help="check at most N unique URLs")
    p.add_argument("--kind", choices=["provider_website", "provider_facebook", "event_url"])
    p.add_argument("--per-host-delay", type=float, default=1.0, help="min seconds between hits to one host")
    p.add_argument("--respect-jobs", action="store_true", help="pause while scrape/backup run")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a text report")
    args = p.parse_args(argv)

    from app.db.database import SessionLocal

    with SessionLocal() as db:
        refs = lh.collect_links(db)
    if args.kind:
        refs = [r for r in refs if r.kind == args.kind]

    report = lh.scan_links(
        refs,
        per_host_delay=args.per_host_delay,
        should_pause=_heavy_job_running if args.respect_jobs else None,
        limit=args.limit,
    )

    counts = report.by_category()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(report.results),
                    "skipped_duplicate_urls": report.skipped_duplicate_urls,
                    "counts": counts,
                    "actionable": [
                        {
                            "url": r.ref.url,
                            "kind": r.ref.kind,
                            "entity_id": r.ref.entity_id,
                            "label": r.ref.label,
                            "category": r.category,
                            "http_status": r.http_status,
                            "detail": r.detail,
                        }
                        for r in report.actionable
                    ],
                },
                indent=2,
            )
        )
        return 0

    total = len(report.results)
    print("=== link health scan (DRY RUN — no writes) ===")
    print(f"checked {total} unique URLs ({report.skipped_duplicate_urls} duplicate URLs skipped)")
    for cat in (lh.OK, lh.BROKEN, lh.UNREACHABLE, lh.BLOCKED_BY_SITE, lh.SSRF_BLOCKED):
        print(f"  {cat:16} {counts.get(cat, 0)}")
    actionable = report.actionable
    print(f"\n--- {len(actionable)} actionable (broken / unreachable) ---")
    for r in sorted(actionable, key=lambda x: (x.ref.kind, x.category)):
        print(f"  [{r.category}] {r.detail} | {r.ref.kind} | {r.ref.label[:40]!r} | {r.ref.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
