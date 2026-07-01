"""De-dupe the name-VARIANT shadow rows the 2026-06-30 search audit flagged.

The general retract_directory_shadow_dupes tool only clusters by normalized name,
so name-VARIANT mirrors at the same address ("Islander Resort" vs "Islander Rv
Resort" vs "Islander Resort Lake Havasu") fell through. This retracts the curated
set: for each cluster the reviewed google_places original is the KEEPER and the
0-review shadow variants are deactivated. Plus the audit's dormant Wake Surf
Adventures (reviews 2-4 yrs old, reviewer reports texts unanswered).

Every target is addressed by explicit prod entity id WITH a name guard, so a
mismatched DB SKIPS. Reversible (Entity.is_active=False + Provider.is_active=False),
snapshotted to scripts/_snapshots/.

Usage:
    .venv\\Scripts\\python.exe scripts/dedup_search_shadow_rows_2026_06_30.py
    .venv\\Scripts\\python.exe scripts/dedup_search_shadow_rows_2026_06_30.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
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

_SNAP_DIR = _ROOT / "scripts" / "_snapshots"

# (entity_id, name-guard, reason). Each is a 0-review shadow variant of a
# reviewed keeper (noted) or an audit-confirmed dormant listing.
_RETRACT: tuple[tuple[str, str, str], ...] = (
    ("20983110-0ad3-47a7-8c42-585e52d0fe58", "islander rv resort",
     "shadow variant of 'Islander Resort' (359 rev)"),
    ("971b3b0f-b5a0-4067-9df7-cac3f96c905e", "islander resort lake havasu",
     "shadow variant of 'Islander Resort' (359 rev)"),
    ("24477f76-d673-46f1-a625-6b7f778847aa", "the spot - pizza",
     "shadow variant of 'The Spot' (712 rev); the arcade-page dup"),
    ("d169d888-0141-415e-82f0-8cb1eac8ab9b", "wake surf adventures",
     "dormant per audit (stale reviews, texts unanswered)"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="De-dupe search shadow rows (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 76)
    print(f"SEARCH SHADOW-ROW DEDUP — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        plans: list[dict] = []
        for eid, guard, reason in _RETRACT:
            ent = db.get(Entity, eid)
            if ent is None or guard not in (ent.name or "").lower():
                print(f"  SKIP {eid}: missing or name mismatch")
                continue
            if not ent.is_active:
                print(f"  OK   {ent.name!r} already inactive")
                continue
            provs = db.query(Provider).filter(Provider.entity_id == eid).all()
            plans.append({
                "entity_id": eid, "name": ent.name, "reason": reason,
                "was_active": ent.is_active,
                "provider_was_active": {p.id: p.is_active for p in provs},
            })
            print(f"  RETRACT  {ent.name[:40]:40s} | {reason}")

        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        tag = "apply" if writing else "dryrun"
        snap = _SNAP_DIR / f"dedup_search_shadow_rows_2026_06_30_snapshot_{tag}_{stamp}.json"
        snap.write_text(json.dumps({"generated_utc": stamp, "db": redacted, "retract": plans},
                                   indent=2, default=str), encoding="utf-8")
        print(f"\nretract count: {len(plans)}   snapshot: {snap.relative_to(_ROOT)}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        for p in plans:
            ent = db.get(Entity, p["entity_id"])
            if ent is not None:
                ent.is_active = False
            for pid in p["provider_was_active"]:
                pr = db.get(Provider, pid)
                if pr is not None:
                    pr.is_active = False
        db.commit()
        print(f"\nAPPLIED: retracted {len(plans)} entities (is_active=False). Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
