"""Batch-9 read-only probe: accuracy field fixes (address/phone garbage).

READ-ONLY. SELECT-only, ZERO writes. Surfaces the flagged field-quality rows so
the operator can confirm the correction before any write. For each target it
prints the CURRENT provider address/phone/website next to the audit's PROPOSED
value + source, and classifies:

  * SOURCED  — audit gives a web-verified replacement; safe to set after a quick
               re-verify.
  * GARBAGE  — bad field but no known-good replacement; needs verification or a
               decision to clear (never invented here).

Nothing is written.

    .venv\\Scripts\\python.exe scripts/audit_directory_batch9_fields_2026_06_27.py
"""

from __future__ import annotations

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

# (name substring, field, confidence, proposed value or None, source note)
_TARGETS: tuple[tuple[str, str, str, str | None, str], ...] = (
    ("amici pools", "address", "SOURCED", "420 El Camino Way Ste 104",
     "Yelp + amicipools.com (current addr is Reinhard's bldg)"),
    ("havasu riviera marina", "address", "SOURCED", "2067 Havasu Riviera Pkwy",
     "havasurivieramarina.com (current is a Plus Code)"),
    ("samons", "phone", "SOURCED", "(928) 855-3302",
     "samonsac.com + Yelp (current 880-2199 unverified)"),
    ("havasu tropical oasis", "address", "GARBAGE", None,
     "addr field holds 'Bobbi Jo 303.909.0056' — no known street addr"),
    ("promised land", "address", "GARBAGE", None,
     "addr field holds an email"),
    ("streamline solar", "address", "GARBAGE", None,
     "addr is just 'Bldg B'"),
    ("greg's trimming", "address", "GARBAGE", None,
     "addr is just 'Quartz Ln' (no number)"),
)


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 82)
    print("BATCH-9 ACCURACY FIELD-FIX PROBE  (READ-ONLY — no rows written)")
    print("=" * 82)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)
        ents = db.query(Entity).filter(
            Entity.is_active.is_(True),
            Entity.entity_type.in_(("commercial", "place")),
        ).all()

        for key, field, conf, proposed, note in _TARGETS:
            matches = [e for e in ents if key in (e.name or "").lower()]
            print("-" * 82)
            print(f"[{conf}] '{key}'  fix {field}")
            print(f"       proposed: {proposed or '(none — needs decision)'}   <- {note}")
            if not matches:
                print("       (no active match — already fixed/retracted?)")
                continue
            if len(matches) > 1:
                print(f"       ⚠ {len(matches)} matches (ambiguous): "
                      + "; ".join(e.name for e in matches[:4]))
            for e in matches:
                prov = sorted(
                    provs_by_entity.get(e.id, []),
                    key=lambda p: -(p.google_review_count or 0),
                )
                pr = prov[0] if prov else None
                cur = getattr(pr, field, None) if pr else None
                website = (pr.website if pr else None) or ""
                print(f"       entity={e.id}")
                print(f"         name : {e.name}")
                print(f"         {field:7s}: {cur!r}")
                print(f"         site : {website}")
        print("-" * 82)
        print("\nREAD-ONLY — nothing written. SOURCED rows: I'll re-verify on the web, then")
        print("propose the exact write. GARBAGE rows: need your call (verify vs clear).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
