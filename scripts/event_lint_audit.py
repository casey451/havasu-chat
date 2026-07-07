"""WS6 read-only event-quality lint audit.

Runs the pure lint rules (:mod:`app.events.lint`) over every LIVE event and
writes a CSV of the rows they flag: the AM/PM-flip candidates and the
venue-hours-as-event rows (spec §14.3). WRITES NOTHING to the catalog — this is
the review input; a human (or a gated fix) resolves what it surfaces.

    .venv\\Scripts\\python.exe scripts\\event_lint_audit.py [--out events_lint.csv]

The repo .env points DATABASE_URL at Railway's INTERNAL host, so this normally
runs in CI (event-lint-audit workflow) where the DB secret resolves.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.lint import lint_event  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only event-quality lint audit.")
    parser.add_argument("--out", default="events_lint_candidates.csv")
    args = parser.parse_args(argv)

    rows: list[tuple[str, str, str, str, str, str]] = []
    with SessionLocal() as db:
        events = db.query(Event).filter(Event.status == "live").all()
        for ev in events:
            for f in lint_event(ev):
                rows.append(
                    (
                        f.rule,
                        f.detail,
                        str(ev.id),
                        str(ev.title or ""),
                        str(ev.date or ""),
                        str(ev.location_name or ""),
                    )
                )

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rule", "detail", "event_id", "title", "date", "location"])
        w.writerows(sorted(rows))

    print(f"events scanned: {len(events)}")
    print(f"lint findings: {len(rows)} -> {out_path}")
    by_rule: dict[str, int] = {}
    for r in rows:
        by_rule[r[0]] = by_rule.get(r[0], 0) + 1
    for rule, n in sorted(by_rule.items()):
        print(f"  {rule}: {n}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
