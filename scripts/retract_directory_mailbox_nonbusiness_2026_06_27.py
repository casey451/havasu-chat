"""Retract non-business mailbox-suite rows (dry-run default; --apply gated).

Directory-audit follow-up (§"Mailbox-as-storefront"). A mailbox address (1642
McCulloch Blvd N — A+ Mail) is LEGITIMATE for a mobile/home-based business
(electrician, notary, tax preparer), so most suites there are real and stay.
Only the NON-business entries are junk. This retracts the intersection of (a) a
1642 McCulloch address and (b) a curated allowlist of confirmed non-businesses:

  * Lake Havasu Marine Assoc. Designated Operator — a program, not a business.
  * Serenity Bay Support Group — a support group filed as Health & Medical.
  * ManyPets Services — national pet-insurance brand at a mailbox (suspect).

Reversible (Entity.is_active=False + Provider.is_active=False).

Usage:
    .venv\\Scripts\\python.exe scripts/retract_directory_mailbox_nonbusiness_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/retract_directory_mailbox_nonbusiness_2026_06_27.py --apply
"""

from __future__ import annotations

import argparse
import re
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
from app.db.models import Provider  # noqa: E402

_MAILBOX_ADDR_RE = re.compile(r"\b1642\s+mcculloch\b", re.IGNORECASE)

# Lowercased name substrings of the confirmed NON-business mailbox rows.
_NONBUSINESS: tuple[str, ...] = (
    "marine association designated",  # Lake Havasu Marine Assoc. Designated Operator (program)
    "serenity bay support",           # support group, not a provider
    "manypets",                       # national pet-insurance brand at a mailbox
)


def _matches(name: str | None) -> bool:
    n = (name or "").lower()
    return any(sub in n for sub in _NONBUSINESS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retract non-business mailbox rows (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: set is_active=False on the matched rows (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 76)
    print(f"MAILBOX NON-BUSINESS RETRACTION — {mode}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        hits = [
            p for p in db.query(Provider).filter(
                Provider.is_active.is_(True), Provider.draft.is_(False)
            ).all()
            if _MAILBOX_ADDR_RE.search((p.address or "")) and _matches(p.provider_name)
        ]
        print(f"matched rows: {len(hits)}\n")
        print("--- rows proposed for retraction (is_active=False) ---")
        for p in sorted(hits, key=lambda p: (p.provider_name or "").lower()):
            print(f"  RETRACT  {(p.provider_name or '')[:46]:46s} | {(p.address or '')[:34]}")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to retract.")
            return 0

        entity_ids = {p.entity_id for p in hits}
        from app.db.models import Entity  # local import: only needed on apply
        n = 0
        for eid in entity_ids:
            ent = db.get(Entity, eid)
            if ent is not None and ent.is_active:
                ent.is_active = False
                n += 1
            for p in db.query(Provider).filter(Provider.entity_id == eid).all():
                p.is_active = False
        db.commit()
        print(f"APPLIED: retracted {n} non-business mailbox entities (is_active=False). Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
