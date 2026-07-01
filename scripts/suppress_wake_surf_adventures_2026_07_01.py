"""Deactivate the dormant "Wake Surf Adventures" listing(s).

Search fix (2026-07-01, item 2): this CVB listing has a placeholder address, no
category tag, and no reviews, yet kept ranking at the top of the Jet Ski &
Watersports leaf for "wake" searches. The durable blocklist
(``app.contrib.ingest_suppression``) stops the daily partner re-scrape from
re-inserting/reactivating it; this one-off deactivates the rows already in prod.

Deactivates both the Provider and its Entity (leaf queries gate on
``Entity.is_active``). Dry-run default; ``--apply --confirm`` gated. Idempotent
(no-ops rows already inactive). Reversible via the printed snapshot.

Usage:
    .venv\\Scripts\\python.exe scripts/suppress_wake_surf_adventures_2026_07_01.py
    .venv\\Scripts\\python.exe scripts/suppress_wake_surf_adventures_2026_07_01.py --apply --confirm
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

from app.contrib.ingest_suppression import is_suppressed_business  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity, Provider  # noqa: E402

_TARGET_NAME = "Wake Surf Adventures"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deactivate dormant Wake Surf Adventures (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 72)
    print(f"SUPPRESS 'Wake Surf Adventures' — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 72)
    print(f"DB target: …@{redacted}\n")

    # Guard: the name must actually be on the durable blocklist, so this script
    # can never deactivate a row the loader would happily re-import.
    if not is_suppressed_business(_TARGET_NAME):
        print(f"ABORT: {_TARGET_NAME!r} is not in SUPPRESSED_BUSINESS_SLUGS — add it first.")
        return 1

    with SessionLocal() as db:
        provs = (
            db.query(Provider).filter(Provider.provider_name == _TARGET_NAME).all()
        )
        if not provs:
            print("No matching Provider rows found — nothing to do.")
            return 0

        to_change = 0
        for p in provs:
            ent = db.get(Entity, p.entity_id) if p.entity_id else None
            ent_active = ent.is_active if ent is not None else None
            already = (not p.is_active) and (ent is None or not ent.is_active)
            flag = "already inactive" if already else "WILL DEACTIVATE"
            if not already:
                to_change += 1
            print(f"  [{p.id}] provider is_active={p.is_active} draft={p.draft} "
                  f"entity={p.entity_id} entity_active={ent_active} -> {flag}")
            print(f"       addr={p.address!r}")

        print(f"\nRows to deactivate: {to_change} of {len(provs)}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        for p in provs:
            p.is_active = False
            ent = db.get(Entity, p.entity_id) if p.entity_id else None
            if ent is not None:
                ent.is_active = False
        db.commit()
        print(f"\nAPPLIED: deactivated {len(provs)} row(s). "
              "Reversible: set is_active=True on the ids above. Blocklist prevents re-import.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
