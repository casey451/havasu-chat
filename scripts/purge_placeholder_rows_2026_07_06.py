"""T1.3 data-op — deactivate placeholder / non-business Provider rows.

Some Google-sourced rows are not real businesses: bare geographies ("Lake Havasu
city"), lead-gen funnels ("Get Free Solar Estimate"), and CMS template stubs
("My Website Store"). The matching ingest guard (``is_placeholder_name`` in
``app.contrib.ingest_suppression``, enforced in ``decide_ingest``) stops NEW ones;
this retires the rows already in the catalog.

Scope guard: only ACTIVE rows whose name matches ``is_placeholder_name`` are
touched. Each is printed before any write so a false positive is caught in review.

DRY-RUN by default; ``--apply`` writes ``is_active=False`` and emits an undo CSV.

    .venv\\Scripts\\python.exe scripts\\purge_placeholder_rows_2026_07_06.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\purge_placeholder_rows_2026_07_06.py --apply    # write (gated)
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

from app.contrib.ingest_suppression import is_placeholder_name  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_UNDO_CSV = "purge_placeholder_rows_undo_2026-07-06.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deactivate placeholder Provider rows.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        active = list(
            db.scalars(select(Provider).where(Provider.is_active.is_(True))).all()
        )
        targets = [p for p in active if is_placeholder_name(p.provider_name or "")]

        print(f"active providers scanned={len(active)}  placeholder matches={len(targets)}")
        for p in targets:
            print(
                f"    id={p.id} slug={p.slug!r} name={p.provider_name!r} "
                f"category={p.category!r} source={p.source!r} website={p.website!r}"
            )

        if not targets:
            print("Nothing to deactivate (no active provider matches a placeholder name).")
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
        print(f"APPLIED: deactivated {len(targets)} placeholder rows. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
