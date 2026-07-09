"""Retract closed / out-of-area / suspect listings (dry-run default; --apply gated).

Directory-audit follow-up (§"out-of-area"/"closed"). Curated, web-verified in the
audit, name-matched, reversible (is_active=False). Targets:

  * Stetson Winery & Event Center — out-of-area (Kingman) + Yelp shows closed.
  * Driftwood Acres Equine Center — out-of-area (Kingman) + Yelp shows closed.
  * Ohmalliancellc — a vape shop that is out of business.
  * Game Spot LLC — the lone "casino" listing; audit could not verify it exists
    at the stated address (resolves to an unrelated pub) — suspect.

dry-run default; --apply gated.

Usage:
    .venv\\Scripts\\python.exe scripts/retract_directory_closed_suspect_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/retract_directory_closed_suspect_2026_06_27.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity, Provider  # noqa: E402

# Lowercased name substrings of audit-confirmed closed/out-of-area/suspect rows.
_RETRACT: tuple[str, ...] = (
    "stetson winery",        # OOA (Kingman) + closed
    "driftwood acres",       # OOA (Kingman) + closed
    "ohmalliancellc",        # out of business (vape)
    "game spot",             # suspect "casino" — unverifiable at stated address
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retract closed/OOA/suspect listings (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: set is_active=False on the matched rows (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 76)
    print(f"CLOSED/OOA/SUSPECT RETRACTION — {mode}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        hits = [
            e for e in db.query(Entity).filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place")),
            ).all()
            if any(sub in (e.name or "").lower() for sub in _RETRACT)
        ]
        print(f"matched entities: {len(hits)}\n")
        for e in sorted(hits, key=lambda e: e.name.lower()):
            print(f"  RETRACT  {e.name[:48]:48s} | src={e.source}")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to retract.")
            return 0

        n = 0
        for e in hits:
            e.is_active = False
            for p in db.query(Provider).filter(Provider.entity_id == e.id).all():
                p.is_active = False
            n += 1
        db.commit()
        print(f"APPLIED: retracted {n} closed/OOA/suspect entities (is_active=False). Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
