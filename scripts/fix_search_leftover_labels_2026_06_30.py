"""Fix the small leftover label data from the 2026-06-30 search audit (gated).

Legacy Provider display fields that read wrong on cards / in chat:
  * Altitude Trampoline Park subcategory "kids-lessons"  -> "attractions"
  * Sunshine Indoor Play     subcategory "cafes-coffee"  -> "attractions"
                             category    "food_drink"    -> "entertainment_attractions"
    (both show the wrong "· Kids Lessons" / "· Cafes Coffee" tag on the Family
    Fun leaf; their PRIMARY leaf is already correct via entity_categories.)
  * Copper Canyon (the cove) category "boat_rental" -> "lake_recreation"
    (the legacy 'boat_rental' string is what made chat call the cove a "boat
    rental"; it belongs to beaches-and-swim-areas / lake recreation.)

Each edit is value-GUARDED (only writes if the current value matches the known
wrong one) so it is idempotent and can't clobber a since-corrected row. Old
values are printed for rollback. Dry-run default; --apply --confirm gated.

Usage:
    .venv\\Scripts\\python.exe scripts/fix_search_leftover_labels_2026_06_30.py
    .venv\\Scripts\\python.exe scripts/fix_search_leftover_labels_2026_06_30.py --apply --confirm
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
from app.db.models import Provider  # noqa: E402

# (provider_id, name-guard, field, expected_old, new_value)
_FIXES: tuple[tuple[str, str, str, str, str], ...] = (
    ("5c8ff1cb-db99-4256-be1f-f02c36fd3b70", "altitude", "subcategory",
     "kids-lessons", "attractions"),
    ("cc532f56-e932-4327-ab18-9e413a621795", "sunshine indoor", "subcategory",
     "cafes-coffee", "attractions"),
    ("cc532f56-e932-4327-ab18-9e413a621795", "sunshine indoor", "category",
     "food_drink", "entertainment_attractions"),
    ("9a19887d-c274-46be-98d3-e620fc036621", "copper canyon", "category",
     "boat_rental", "lake_recreation"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fix leftover label data (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 74)
    print(f"FIX LEFTOVER LABEL DATA — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 74)
    print(f"DB target: …@{redacted}\n")

    changed = 0
    with SessionLocal() as db:
        for pid, guard, field, old, new in _FIXES:
            p = db.get(Provider, pid)
            if p is None or guard not in (p.provider_name or "").lower():
                print(f"  SKIP {pid}: missing or name mismatch")
                continue
            cur = getattr(p, field)
            if cur == new:
                print(f"  OK   {p.provider_name[:26]:26s} {field} already {new!r}")
                continue
            if cur != old:
                print(f"  SKIP {p.provider_name[:26]:26s} {field}={cur!r} (expected {old!r})")
                continue
            print(f"  FIX  {p.provider_name[:26]:26s} {field}: {old!r} -> {new!r}")
            if writing:
                setattr(p, field, new)
            changed += 1
        if writing:
            db.commit()

    print(f"\n{'CHANGED' if writing else 'would change'}: {changed} field(s).")
    if not writing:
        print("DRY RUN — nothing written. Re-run with --apply --confirm after approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
