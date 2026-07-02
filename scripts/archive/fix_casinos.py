"""§6.7 Casinos — PRECISE, by-id fixes only (2026-06-14).

An earlier version matched casino names by substring and would have wrongly
soft-hidden local businesses ("Bluewater Accounting & Tax Services", "Blue Water
Pool Services", "Bluewater Jetboat Tours"). The inspect_casinos.py read-only pass
showed the real picture, so this version touches ONLY specific rows by id.

Findings + resulting actions:
  * BlueWater Resort & Casino (Parker, id 0a6f9ff1…) — already soft-hidden by the
    §6.8 locality sweep. No action here.
  * Havasu Landing Resort & Casino (active, id 2aca6724…) — already has a website
    (http://havasulandingresortcasino.com). This script only normalizes it to the
    canonical https URL (idempotent). The brief's "no website" item is already
    effectively resolved.
  * "Game Spot llc" (id f4814d5b…) and "Win Win Bingo Casino" (id 2880c8f3…) are
    REAL local Lake Havasu businesses (valid in-town addresses). They are NOT
    auto-touched — left for Casey's call on whether they belong in a gaming list.

Gate (CLAUDE.md): READ-ONLY by default; writes only with ``--apply``. The single
write is a website-string normalization on one known id (no deletes, no hides).

Run from repo root with the prod venv:
    .venv\\Scripts\\python.exe scripts\\fix_casinos.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\fix_casinos.py --apply     # apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# The single active Havasu Landing Resort & Casino row (from inspect_casinos.py).
HAVASU_LANDING_ID = "2aca6724-669a-4a3a-bfbd-d08a53d06528"
CANONICAL_WEBSITE = "https://havasulandingresortcasino.com/"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform the write (default: dry-run)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        p = db.get(Provider, HAVASU_LANDING_ID)
        if p is None:
            print(f"ABORT: no Provider with id={HAVASU_LANDING_ID} "
                  "(re-run inspect_casinos.py to refresh the id).")
            return 2

        print(f"Havasu Landing row: {p.provider_name!r}")
        print(f"  current website: {p.website!r}")
        if p.website == CANONICAL_WEBSITE:
            print("  already canonical — nothing to do.")
            return 0

        print(f"  WOULD SET website -> {CANONICAL_WEBSITE}")
        if not args.apply:
            print("\nDRY-RUN: re-run with --apply to write.")
            return 0

        p.website = CANONICAL_WEBSITE
        db.commit()
        print("\nAPPLIED: website normalized.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
