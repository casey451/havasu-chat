"""Batch-9 accuracy field fixes: clean garbage address/phone fields (dry-run default; --apply gated).

Directory-audit follow-up. Operator-approved 2026-06-28. Each fix is either:
  * a junk-PREFIX strip — the correct street address was already present in the
    field behind a Plus Code / email / "Bldg B" prefix (no invented data); or
  * a web-VERIFIED replacement (Amici address, Samons phone — confirmed against
    the operator site + Yelp on 2026-06-28).

Writes the chosen field on the entity's best-reviewed active Provider (the
canonical record the leaf renders). Single-match guard: a key matching 0 or >1
active entities is reported and SKIPPED. Old value snapshotted for rollback.
Reversible.

EXCLUDED (need an operator decision — no recoverable value, never invented):
  * Havasu Tropical Oasis Floating Rentals — addr is "Bobbi Jo 303.909.0056"
  * Greg's Trimmings Services           — addr is "Quartz Ln" (no street number)

PROD GATE (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/fix_directory_fields_batch9_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/fix_directory_fields_batch9_2026_06_27.py --apply
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

# (matcher, exact_name?, field, new_value, note)
_FIXES: tuple[tuple[str, bool, str, str, str], ...] = (
    ("amici pools", False, "address",
     "420 El Camino Way Ste 104, Lake Havasu City, AZ 86403, USA",
     "web-verified (Yelp + amicipools.com); was Reinhard's W Acoma bldg"),
    ("samons", False, "phone", "(928) 855-3302",
     "web-verified (samonsac.com + Yelp); was 880-2199"),
    ("havasu riviera marina", True, "address",
     "2067 Havasu Riviera Pkwy, Lake Havasu City, AZ 86406, USA",
     "strip 'CMVJ+G2,' Plus Code prefix"),
    ("the promised land landscaping svc", True, "address",
     "2850 Bamboo Dr, Lake Havasu City, AZ 86404, USA",
     "strip email/'call for appointment' prefix"),
    ("streamline solar", False, "address",
     "1080 Aviation Dr STE 112, Lake Havasu City, AZ 86404, USA",
     "strip 'Bldg B,' prefix"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-9 accuracy field fixes (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: set the corrected field (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 80)
    print(f"BATCH-9 ACCURACY FIELD FIXES — {mode}")
    print("=" * 80)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        ents = db.query(Entity).filter(
            Entity.is_active.is_(True),
            Entity.entity_type.in_(("commercial", "place")),
        ).all()

        planned: list[tuple[Provider, str, str, str, str]] = []  # prov, field, old, new, note
        for key, exact, field, new_val, note in _FIXES:
            if exact:
                cands = [e for e in ents if (e.name or "").lower() == key]
            else:
                cands = [e for e in ents if key in (e.name or "").lower()]
            if not cands:
                print(f"  SKIP  '{key}': no active entity match")
                continue
            if len(cands) > 1:
                print(f"  SKIP  '{key}': {len(cands)} matches (ambiguous) — "
                      + "; ".join(e.name for e in cands[:4]))
                continue
            provs = sorted(provs_by_entity.get(cands[0].id, []),
                           key=lambda p: -(p.google_review_count or 0))
            active = [p for p in provs if p.is_active]
            if not active:
                print(f"  SKIP  '{cands[0].name}': no active provider")
                continue
            prov = active[0]
            old = getattr(prov, field, None) or ""
            if old.strip() == new_val.strip():
                print(f"  OK    '{cands[0].name}': {field} already correct")
                continue
            planned.append((prov, field, old, new_val, note))

        print(f"\nfield fixes planned: {len(planned)}\n")
        for prov, field, old, new_val, note in planned:
            print(f"  FIX  {prov.provider_name[:28]:28s} {field}")
            print(f"        old: {old}")
            print(f"        new: {new_val}   ({note})")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to apply.")
            return 0

        print("--- snapshot (provider_id, field, old -> new) ---")
        for prov, field, old, new_val, _note in planned:
            print(f"  {prov.id}  {field}: {old!r} -> {new_val!r}")
            setattr(prov, field, new_val)
        db.commit()
        print(f"\nAPPLIED: corrected {len(planned)} fields. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
