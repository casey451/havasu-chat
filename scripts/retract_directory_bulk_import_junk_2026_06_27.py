"""Retract bulk-import junk: generic non-businesses + out-of-area (gated).

Directory-audit follow-up (§"Purge the bulk-import junk"). dry-run default;
--apply gated. Targets ONLY rows that BOTH (a) carry the bulk-import placeholder
address "Go Lake Havasu Visitor Center" AND (b) match a hand-curated, web-
verified allowlist of names that are clearly NOT a Lake-Havasu-City business:

  * generic non-listings — "Bird Watching", "Splash Pads", "Outdoor
    Enthusiasts", "Boat-In Beaches & Campsites", "Downtown District".
  * out-of-area landmarks/venues — Hoover Dam (NV), Blythe Intaglios (CA),
    Topock/Mystic Maze (CA), Black Meadow Landing + Diner (Parker Dam CA),
    Havasu Landing Resort & Casino (Havasu Lake CA), Ghost Mine Saloon (Oatman),
    Havasu National Wildlife Refuge (Parker area), London Bridge Jet Boat Tour
    (Parker area).

The REAL businesses in the same placeholder-address set (shuttles, fishing
guides, charters, realty, vacation-rental mgmt) are deliberately NOT touched
here — they need an address fix, not retraction. Matching is the intersection
of the placeholder-address signature and the name allowlist, so a future real
business that happens to share a name can't be swept in unless it also carries
the placeholder address.

Retraction is REVERSIBLE: Entity.is_active=False (+ Provider.is_active=False).

Usage:
    .venv\\Scripts\\python.exe scripts/retract_directory_bulk_import_junk_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/retract_directory_bulk_import_junk_2026_06_27.py --apply
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
from app.db.models import Entity, Provider  # noqa: E402

_VISITOR_CENTER_ADDR_RE = re.compile(r"go\s+lake\s+havasu\s+visitor\s+center", re.IGNORECASE)

# Lowercase name PREFIXES of audit-confirmed generic/out-of-area rows. Prefix
# match folds in variants ("Bird Watching" + "Bird Watching in the Havasu NWR";
# "Black Meadow Landing" + "Black Meadow Landing Diner").
_JUNK_PREFIXES: tuple[str, ...] = (
    # generic non-businesses
    "bird watching",
    "boat-in beaches",
    "outdoor enthusiasts",
    "splash pads",
    "downtown district",
    # out-of-area landmarks / venues (web-verified in the audit)
    "hoover dam",
    "blythe intaglios",
    "topock maze",
    "black meadow landing",
    "havasu landing resort",
    "ghost mine saloon",
    "havasu national wildlife refuge",
    "london bridge jet boat tour",
)


def _matches_junk(name: str | None) -> bool:
    n = (name or "").strip().lower()
    return any(n.startswith(p) for p in _JUNK_PREFIXES)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retract bulk-import junk (gated).")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE: set is_active=False on the matched rows (default: dry run)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    mode = "APPLY (writing)" if args.apply else "DRY RUN (no writes)"
    print("=" * 76)
    print(f"BULK-IMPORT JUNK RETRACTION — {mode}")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        # Candidate Providers carrying the placeholder address.
        providers = (
            db.query(Provider)
            .filter(Provider.is_active.is_(True), Provider.draft.is_(False))
            .all()
        )
        prov_hits = [
            p for p in providers
            if _VISITOR_CENTER_ADDR_RE.search((p.address or ""))
            and _matches_junk(p.provider_name)
        ]
        # Some junk rows are provider-less place ENTITIES (no Provider address);
        # match those by name + their location/contact carrying the placeholder.
        prov_entity_ids = {p.entity_id for p in prov_hits}
        ent_hits: list[Entity] = []
        for e in (
            db.query(Entity)
            .filter(Entity.is_active.is_(True), Entity.entity_type.in_(("commercial", "place")))
            .all()
        ):
            if e.id in prov_entity_ids or not _matches_junk(e.name):
                continue
            loc = getattr(e, "location", None)
            addr = (getattr(loc, "address_normalized", "") or "") if loc else ""
            if _VISITOR_CENTER_ADDR_RE.search(addr):
                ent_hits.append(e)

        target_entity_ids = set(prov_entity_ids) | {e.id for e in ent_hits}
        print(f"provider rows matched:   {len(prov_hits)}")
        print(f"place-entity rows matched: {len(ent_hits)}")
        print(f"distinct entities:       {len(target_entity_ids)}\n")

        print("--- rows proposed for retraction (is_active=False) ---")
        for p in sorted(prov_hits, key=lambda p: (p.provider_name or "").lower()):
            print(f"  RETRACT  {(p.provider_name or '')[:44]:44s} | cat={p.primary_category} (provider)")
        for e in sorted(ent_hits, key=lambda e: e.name.lower()):
            print(f"  RETRACT  {e.name[:44]:44s} | (place entity)")
        print()

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply (after approval) to retract.")
            return 0

        n_ent = 0
        for eid in target_entity_ids:
            ent = db.get(Entity, eid)
            if ent is not None and ent.is_active:
                ent.is_active = False
                n_ent += 1
            for p in db.query(Provider).filter(Provider.entity_id == eid).all():
                p.is_active = False
        db.commit()
        print(f"APPLIED: retracted {n_ent} junk entities (is_active=False). Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
