"""Batch-8 read-only probe: priority-cluster (boats/pools/HVAC/roofing) duplicate pairs.

READ-ONLY. SELECT-only, ZERO writes. The dry-run / show-counts step before any
operator-approved retraction. Surfaces the specific duplicate clusters the
directory audit flagged in the priority cluster, so the operator can confirm
keep/drop per cluster. For each cluster it lists every matching ACTIVE
commercial/place entity with: review count, source, phone, address, primary
category, and is_active — exposing the "real reviewed listing + thin 0-review
mirror" shape (and showing which were already cleared by earlier batches).

Clusters are tagged by confidence:
  * AUTO  — unambiguous real+thin mirror; safe to retract the thin one.
  * HOLD  — needs human judgment (a real-world MERGER, or "distinct vs name
            variant" that the audit itself marked [verify]). Never auto-dropped.

Nothing is retracted here.

    .venv\\Scripts\\python.exe scripts/audit_directory_batch8_dedup_2026_06_27.py
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

# (cluster label, match substrings, confidence, note)
_CLUSTERS: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("Boat Broker", ("boat broker",), "AUTO",
     "keep reviewed 1680 Industrial; drop thin 'New' mirror / orphan slug"),
    ("Lake Havasu Marina", ("lake havasu marina",), "AUTO",
     "keep reviewed 1100 McCulloch; drop offsite-link mirror"),
    ("Paradise Wild Wave", ("paradise wild wave",), "AUTO",
     "3 entries same phone — keep the reviewed one"),
    ("TikiToons", ("tikitoons",), "AUTO",
     "Tikitoons / Arizona TikiToons same phone — keep reviewed"),
    ("WACKO Kayak", ("wacko",), "AUTO", "x2 — keep reviewed"),
    ("Lake Havasu Airboat", ("airboat",), "AUTO", "x2 — keep reviewed"),
    ("J C Marine", ("j c marine", "jc marine"), "AUTO",
     "J C Marine vs JC Marine same addr/phone — keep reviewed, merge stub"),
    ("Pro Marine", ("pro-marine", "pro marine"), "AUTO",
     "Pro-Marine vs Pro Marine Engines same addr/phone — keep reviewed"),
    ("Ambient Edge / Fayette", ("ambient edge", "fayette"), "HOLD",
     "real-world MERGER (Ambient acquired Fayette 2025); keep one + alias — judgment"),
    ("TNT / Dynamite Roofing", ("tnt roofing", "dynamite roofing"), "HOLD",
     "shared phone — 'likely one operator/DBA' [verify] before consolidating"),
    ("Mohave Roofing", ("mohave roofing",), "HOLD",
     "x2 — [verify] distinct facility vs name variant"),
)


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 80)
    print("BATCH-8 PRIORITY-CLUSTER DEDUP PROBE  (READ-ONLY — no rows written)")
    print("=" * 80)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        # All providers by entity (best-reviewed wins) for the real-vs-thin signal.
        prov_by_entity: dict[str, Provider] = {}
        for p in db.query(Provider).all():
            cur = prov_by_entity.get(p.entity_id)
            if cur is None or (p.google_review_count or 0) > (cur.google_review_count or 0):
                prov_by_entity[p.entity_id] = p

        ents = (
            db.query(Entity)
            .filter(Entity.entity_type.in_(("commercial", "place")))
            .all()
        )

        def rev(e: Entity) -> int:
            pr = prov_by_entity.get(e.id)
            return (pr.google_review_count or 0) if pr else 0

        for label, subs, conf, note in _CLUSTERS:
            members = [
                e for e in ents
                if any(s in (e.name or "").lower() for s in subs)
            ]
            active = [e for e in members if e.is_active]
            print("-" * 80)
            print(f"[{conf}] {label}   (active members: {len(active)} / total {len(members)})")
            print(f"       {note}")
            if not members:
                print("       (no matching entities — already retracted/renamed?)")
                continue
            for e in sorted(members, key=lambda e: (-int(e.is_active), -rev(e))):
                pr = prov_by_entity.get(e.id)
                backed = "prov" if pr else "PLACE"
                phone = (pr.phone if pr else "") or ""
                addr = (pr.address if pr else "") or ""
                act = "ACTIVE " if e.is_active else "retired"
                print(f"   {act} [{backed:5s}] rev={rev(e):>4d} src={e.source[:12]:12s} "
                      f"{e.name[:30]:30s} | {phone[:14]:14s} | {addr[:30]}")
        print("-" * 80)
        print("\nREAD-ONLY — nothing written. AUTO clusters: I'll retract the thin 0-review")
        print("mirror (keep the reviewed listing). HOLD clusters wait for your call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
