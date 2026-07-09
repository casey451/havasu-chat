"""T1.1 data-op — deactivate permanently-closed golf venues (S4 liveness guard).

The curated golf set stopped emitting Havasu Island Golf Course (closed 2018),
but a live Provider row may still exist in the catalog from an earlier load or a
Google-sourced import — a closed course shown as "Open daily" is the worst kind
of directory error. This deactivates any ACTIVE Provider whose name matches
:data:`app.contrib.lhc_golf.CLOSED_VENUES` (name-normalized via ``is_closed_venue``).

Scope guard: only rows that are currently ``is_active=True`` and whose normalized
name is in the closed set are touched. It is deliberately name-driven (not a golf
category filter) so a mis-categorized closed row is still caught.

DRY-RUN by default (no writes); ``--apply`` writes ``is_active=False`` and emits
an undo CSV so the change is reversible.

    .venv\\Scripts\\python.exe scripts\\deactivate_closed_golf_2026_07_06.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\deactivate_closed_golf_2026_07_06.py --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.lhc_golf import is_closed_venue  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_UNDO_CSV = "deactivate_closed_golf_undo_2026-07-06.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deactivate permanently-closed golf venues.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        active = list(
            db.scalars(select(Provider).where(Provider.is_active.is_(True))).all()
        )
        targets = [p for p in active if is_closed_venue(p.provider_name or "")]

        print(f"active providers scanned={len(active)}  closed-venue matches={len(targets)}")
        for p in targets:
            print(
                f"    id={p.id} slug={p.slug!r} name={p.provider_name!r} "
                f"category={p.category!r} source={p.source!r}"
            )

        if not targets:
            print("Nothing to deactivate (no active provider matches a CLOSED_VENUE).")
            return 0

        if not args.apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
            return 0

        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "slug", "provider_name", "old_is_active"])
            for p in targets:
                w.writerow([p.id, p.slug, p.provider_name, p.is_active])

        for p in targets:
            p.is_active = False
        db.commit()
        print(f"APPLIED: deactivated {len(targets)} closed-venue rows. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
