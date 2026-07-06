"""T4.2 — clean golf provider descriptions polluted with "Hours:"/"Details:".

The old ``_facility_description`` folded blurb + "Hours: …" + "Details: <url>" into
one description (fixed forward). This resets the About text of the existing golf
providers to just the curated blurb. Match is by normalized name against the
curated ``IN_TOWN_VENUES``; only rows whose stored description differs are touched.

DRY-RUN by default; ``--apply`` writes and emits an undo CSV.

    .venv\\Scripts\\python.exe scripts\\clean_golf_descriptions_2026_07_06.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\clean_golf_descriptions_2026_07_06.py --apply    # write (gated)
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

from app.contrib.lhc_golf import IN_TOWN_VENUES, _normalize_venue_name  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_UNDO_CSV = "clean_golf_descriptions_undo_2026-07-06.csv"
_BLURB_BY_NAME = {_normalize_venue_name(v.name): (v.blurb or "") for v in IN_TOWN_VENUES}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean polluted golf descriptions.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        golf = db.scalars(
            select(Provider).where(Provider.source.like("%lhc_golf%"), Provider.is_active.is_(True))
        ).all()
        targets: list[tuple[Provider, str]] = []
        for p in golf:
            desc = p.description or ""
            # ONLY the curated-sourced rows carry the "Hours:"/"Details:" pollution
            # marker. A google-sourced description (Golf N' Brews' "LET's PLAY…") has
            # neither and is the richer real About text — never overwrite it.
            if "Hours:" not in desc and "Details:" not in desc:
                continue
            blurb = _BLURB_BY_NAME.get(_normalize_venue_name(p.provider_name or ""))
            if blurb and desc != blurb:
                targets.append((p, blurb))

        print(f"active lhc_golf providers={len(golf)}  would clean={len(targets)}")
        for p, blurb in targets:
            print(f"    {p.provider_name!r}\n       OLD: {(p.description or '')[:80]!r}\n       NEW: {blurb[:80]!r}")

        if not targets:
            print("Nothing to clean.")
            return 0
        if not args.apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
            return 0

        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "provider_name", "old_description"])
            for p, _ in targets:
                w.writerow([p.id, p.provider_name, p.description])

        for p, blurb in targets:
            p.description = blurb
        db.commit()
        print(f"APPLIED: cleaned {len(targets)} descriptions. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
