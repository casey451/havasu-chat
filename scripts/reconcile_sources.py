"""Coverage reconciliation: prove every in-area source listing/event is on Ask
Hava, or excluded with a reason (Part B of the source-parity plan).

Enumerates golakehavasu's partner directory + River Scene's event sitemap,
matches each item against our providers/events, and classifies it:

  * ``matched``        — present, and (businesses) filed in the crosswalk leaf.
  * ``miscategorized`` — present, but our leaf != the crosswalk leaf.
  * ``missing``        — in-area, not found on Ask Hava.
  * ``excluded``       — out-of-area (Casey's Lake-Havasu-only decision) or on a
                         suppression list, with a logged reason.

The completeness invariant: a green run has 0 ``missing`` + 0 ``miscategorized``
and every ``excluded`` row carries a reason.

REPORT-ONLY by default: writes a Markdown + CSV summary to docs/audits/ and
prints counts; it does NOT mutate providers/events. ``--persist-ledger`` also
upserts the source_listings / source_events bookkeeping tables (safe, additive).

Usage:
    .venv\\Scripts\\python.exe scripts\\reconcile_sources.py --limit 25
    .venv\\Scripts\\python.exe scripts\\reconcile_sources.py --businesses-only
    .venv\\Scripts\\python.exe scripts\\reconcile_sources.py --persist-ledger
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.reconcile_core import (  # noqa: E402
    ReconcileRow,
    invariant_green,
    summarize,
)


def write_report(rows: list[ReconcileRow], out_dir: Path, stamp: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"reconcile_sources_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["source", "source_url", "source_category", "name", "region",
             "mapped", "match_status", "matched_id", "exclusion_reason"]
        )
        for r in rows:
            w.writerow([r.source, r.source_url, r.source_category, r.name, r.region,
                        r.mapped, r.match_status, r.matched_id, r.exclusion_reason])

    counts = summarize(rows)
    md_path = out_dir / f"reconcile_sources_{stamp}.md"
    lines = [
        f"# Source reconciliation — {stamp}",
        "",
        f"Total items: {len(rows)}",
        "",
        "| status | count |",
        "|---|---|",
    ]
    for status in ("matched", "miscategorized", "missing", "excluded", "excluded_without_reason"):
        lines.append(f"| {status} | {counts.get(status, 0)} |")
    green = invariant_green(counts)
    lines += ["", f"**Invariant:** {'GREEN ✅' if green else 'RED ❌ — see below'}", ""]
    for status in ("missing", "miscategorized"):
        bad = [r for r in rows if r.match_status == status]
        if bad:
            lines += [f"## {status} ({len(bad)})", ""]
            for r in bad[:200]:
                lines.append(
                    f"- `{r.source}` **{r.name}** — {r.source_category} → {r.mapped} ({r.source_url})"
                )
            lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, csv_path


def main() -> int:  # pragma: no cover - live crawl orchestration
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap items per source (testing).")
    parser.add_argument("--businesses-only", action="store_true")
    parser.add_argument("--events-only", action="store_true")
    parser.add_argument("--persist-ledger", action="store_true", help="Also upsert the ledger tables.")
    parser.add_argument("--out-dir", type=str, default="docs/audits/2026-07")
    args = parser.parse_args()

    from app.contrib.reconcile_live import (
        crawl_business_rows,
        crawl_event_rows,
        persist_ledger,
    )

    rows: list[ReconcileRow] = []
    if not args.events_only:
        rows += crawl_business_rows(limit=args.limit)
    if not args.businesses_only:
        rows += crawl_event_rows(limit=args.limit)

    stamp = date.today().isoformat()
    md, csvp = write_report(rows, Path(args.out_dir), stamp)
    counts = summarize(rows)
    print(f"items={len(rows)} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"report: {md}\n        {csvp}")
    print(f"invariant: {'GREEN' if invariant_green(counts) else 'RED'}")
    if args.persist_ledger:
        n = persist_ledger(rows)
        print(f"ledger rows upserted: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
