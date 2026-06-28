"""Retract thin shadow-duplicate mirrors (dry-run default; --apply gated).

Directory-audit follow-up (§"De-duplicate"). For each cluster of ACTIVE
directory entities (commercial/place) sharing a normalized name, AUTO-RETRACT
fires ONLY on the unambiguous "real listing + thin mirror" shape:

  KEEPER  — exactly ONE member is provider-backed with google_review_count > 0
            (the canonical, reviewed original). If 0 or >1 members are reviewed
            (a chain, or no clear original), the whole cluster is SKIPPED.
  MIRROR  — any OTHER member that is thin AND was NOT sourced from google_places:
            review count 0/NULL and source in the shadow-import set
            (go_lake_havasu / admin / lhc_funzone / pdga / manual:*). A
            google_places row is NEVER retracted here, even at 0 reviews (could
            be a real but new business) — those are left for manual review.

Retraction is REVERSIBLE: Entity.is_active=False (+ Provider.is_active=False if
the mirror has one). No deletes. This is the apply half of the
dry-run -> show-counts -> approve -> apply protocol; the real run requires
--apply AND the operator's explicit go.

Usage:
    .venv\\Scripts\\python.exe scripts/retract_directory_shadow_dupes_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/retract_directory_shadow_dupes_2026_06_27.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
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

# Sources that produced thin shadow mirrors of real Google listings. A 0-review
# member from one of these (or any provider-less place) is a retract candidate;
# a google_places row never is.
_SHADOW_SOURCES = {"go_lake_havasu", "admin", "lhc_funzone", "pdga"}


def _norm_name(s: str | None) -> str:
    n = (s or "").lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\b(llc|inc|incorporated|co|corp|ltd|the)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _is_shadow_source(src: str | None) -> bool:
    s = (src or "").strip().lower()
    return s in _SHADOW_SOURCES or s.startswith("manual:")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retract thin shadow-dupe mirrors (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: set is_active=False on the mirror rows (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 76)
    print(f"SHADOW-DUPE MIRROR RETRACTION — {mode}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        entities = (
            db.query(Entity)
            .filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place")),
            )
            .all()
        )
        # Best (max-reviewed) active provider per entity.
        prov_by_entity: dict[str, Provider] = {}
        for p in db.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        ).all():
            cur = prov_by_entity.get(p.entity_id)
            if cur is None or (p.google_review_count or 0) > (cur.google_review_count or 0):
                prov_by_entity[p.entity_id] = p

        def _rev(e: Entity) -> int:
            pr = prov_by_entity.get(e.id)
            return (pr.google_review_count or 0) if pr else 0

        clusters: dict[str, list[Entity]] = defaultdict(list)
        for e in entities:
            key = _norm_name(e.name)
            if key:
                clusters[key].append(e)

        to_retract: list[tuple[Entity, Entity]] = []  # (mirror, keeper)
        skipped: list[tuple[str, str]] = []  # (cluster, reason)
        for key, rows in clusters.items():
            if len(rows) < 2:
                continue
            reviewed = [e for e in rows if e.id in prov_by_entity and _rev(e) > 0]
            if len(reviewed) != 1:
                reason = "no reviewed keeper" if not reviewed else f"{len(reviewed)} reviewed (chain?)"
                skipped.append((key, reason))
                continue
            keeper = reviewed[0]
            mirrors = [
                e for e in rows
                if e.id != keeper.id and _rev(e) == 0 and _is_shadow_source(e.source)
            ]
            # A non-shadow, non-keeper member (e.g. a 0-review google_places dup)
            # blocks nothing but is noted — we just don't touch it.
            non_shadow_dups = [
                e for e in rows
                if e.id != keeper.id and e not in mirrors
            ]
            if not mirrors:
                skipped.append((key, "no shadow-source mirror to retract"))
                continue
            for m in mirrors:
                to_retract.append((m, keeper))
            if non_shadow_dups:
                skipped.append((key, f"{len(non_shadow_dups)} non-shadow dup kept (manual)"))

        print(f"clusters scanned:        {sum(1 for r in clusters.values() if len(r) >= 2)}")
        print(f"mirrors to retract:      {len(to_retract)}")
        print(f"clusters skipped:        {len(skipped)} (chains / no clear keeper / STRs)\n")

        print("--- mirrors proposed for retraction (is_active=False) ---")
        for mirror, keeper in sorted(to_retract, key=lambda mk: mk[0].name.lower()):
            kp = prov_by_entity.get(keeper.id)
            print(f"  RETRACT  {mirror.name[:36]:36s} src={mirror.source[:14]:14s} "
                  f"| KEEP {keeper.name[:24]:24s} (rev={kp.google_review_count if kp else 0})")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to retract.")
            return 0

        n = 0
        for mirror, _keeper in to_retract:
            mirror.is_active = False
            for p in db.query(Provider).filter(Provider.entity_id == mirror.id).all():
                p.is_active = False
            n += 1
        db.commit()
        print(f"APPLIED: retracted {n} shadow-mirror entities (is_active=False). Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
