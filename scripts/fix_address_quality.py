"""WS-4 (Track B2) — mechanical address-quality fixes on Location + Provider.

The 2026-06-10 prod prep sized the queues (3,242 location rows): 377 with the
city name repeated inside ``address`` (the loader-concatenation artifact the
format_address pre-strip now prevents), 976 missing ``zip``, 1 empty, 1
double-comma. This script handles exactly the MECHANICAL subset:

  1. city-repeat collapse — rows whose address mentions "lake havasu" 2+
     times are rebuilt to one canonical ``street, Lake Havasu City, AZ [zip]``
     via app.core.address.normalize_full_address (which refuses anything that
     needs human judgment — those stay for the portal flag queue);
  2. comma/whitespace-run cleanup on the same normalizer;
  3. zip text-backfill — rows missing ``zip`` whose own address text carries a
     Lake-Havasu-shaped zip (864xx) get it parsed into the column. (The
     lat/lng-based backfill for addresses with NO zip in text is a separate,
     external-API pass — out of scope here.)

NOT here, on purpose: the 812 no-leading-street-number rows (parks, trails,
areas — many legit) surface in the admin portal's address-flags queue for
pattern review, never auto-fix.

Both Location rows and their mirrored Provider.address/zip are fixed in the
same pass so the legacy and entity reads stay consistent.

Safety (CLAUDE.md prod-data rules, apply_taxonomy_remap.py pattern):
DRY-RUN default printing per-row before/after + counts -> Casey approves ->
``--apply --confirm`` writes in one transaction after a JSON rollback
snapshot of every touched row.

Usage:
    python scripts/fix_address_quality.py                # dry run
    python scripts/fix_address_quality.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.core.address import normalize_full_address, parse_zip  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _needs_mechanical_fix(address: str | None) -> bool:
    """Scope gate: only the shapes the prep counted as mechanical."""
    if not address:
        return False
    low = address.lower()
    return (
        low.count("lake havasu") >= 2
        or ",," in address.replace(", ,", ",,")
        or "  " in address
    )


def run(*, apply: bool = False, confirm: bool = False,
        snapshot_dir: Path | None = None, session=None) -> dict:
    from app.db.models import Location, Provider

    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts = {
        "locations_scanned": 0,
        "address_fixed": 0,
        "address_needs_review": 0,
        "zip_backfilled": 0,
        "provider_rows_synced": 0,
    }
    try:
        print(f"DB target: {_sanitized_target()}\n")
        locations = session.query(Location).all()
        counts["locations_scanned"] = len(locations)

        # entity_id -> Provider for the mirrored legacy columns.
        providers_by_entity = {
            p.entity_id: p
            for p in session.query(Provider).filter(Provider.entity_id.isnot(None))
        }

        addr_plan: list[tuple[object, str, str]] = []  # (loc, old, new)
        review: list[tuple[object, str]] = []
        zip_plan: list[tuple[object, str]] = []  # (loc, zip)

        for loc in locations:
            addr = loc.address
            if _needs_mechanical_fix(addr):
                fixed = normalize_full_address(addr)
                if fixed:
                    addr_plan.append((loc, addr, fixed))
                elif (addr or "").lower().count("lake havasu") >= 2:
                    review.append((loc, addr))
            if not (loc.zip or "").strip():
                z = parse_zip(loc.address)
                if z:
                    zip_plan.append((loc, z))

        counts["address_fixed"] = len(addr_plan)
        counts["address_needs_review"] = len(review)
        counts["zip_backfilled"] = len(zip_plan)

        print(f"locations scanned:          {counts['locations_scanned']}")
        print(f"address mechanical fixes:   {len(addr_plan)}")
        print(f"city-repeat needs review:   {len(review)} (left for the portal queue)")
        print(f"zip backfills (from text):  {len(zip_plan)}\n")

        for loc, old, new in addr_plan:
            print(f"FIX  location {loc.id} (entity {loc.entity_id})")
            print(f"     - {old!r}")
            print(f"     + {new!r}")
        if review:
            print("\nNeeds human review (not auto-fixed):")
            for loc, addr in review:
                print(f"HOLD location {loc.id}: {addr!r}")
        if zip_plan:
            print("\nZip backfills:")
            for loc, z in zip_plan[:20]:
                print(f"ZIP  location {loc.id}: {z}  (from {loc.address!r})")
            if len(zip_plan) > 20:
                print(f"     ... and {len(zip_plan) - 20} more")

        if not apply:
            print("\nDRY RUN — nothing written. Show Casey the counts; re-run "
                  "with --apply --confirm after approval.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                  f"{_sanitized_target()}.")
            return counts

        # Rollback snapshot of every row we may touch (locations + providers).
        touched_locs = {loc.id: loc for loc, *_ in addr_plan}
        touched_locs.update({loc.id: loc for loc, _ in zip_plan})
        snapshot = {
            "locations": [
                {"id": loc.id, "entity_id": loc.entity_id, "address": loc.address,
                 "zip": loc.zip, "address_normalized": loc.address_normalized}
                for loc in touched_locs.values()
            ],
            "providers": [
                {"id": p.id, "entity_id": p.entity_id, "address": p.address, "zip": p.zip}
                for p in (
                    providers_by_entity.get(loc.entity_id)
                    for loc in touched_locs.values()
                )
                if p is not None
            ],
        }
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"address_quality_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} "
              f"({len(snapshot['locations'])} locations, "
              f"{len(snapshot['providers'])} providers)")

        # One transaction: addresses + zips, locations + mirrored providers.
        synced = 0
        for loc, old, new in addr_plan:
            loc.address = new[:255]
            loc.address_normalized = new.lower()[:255]
            prov = providers_by_entity.get(loc.entity_id)
            if prov is not None and (prov.address or "").strip() == old.strip():
                prov.address = new
                synced += 1
        for loc, z in zip_plan:
            loc.zip = z
            prov = providers_by_entity.get(loc.entity_id)
            if prov is not None and not (prov.zip or "").strip():
                prov.zip = z
                synced += 1
        session.commit()
        counts["provider_rows_synced"] = synced
        print(f"APPLIED — {len(addr_plan)} addresses, {len(zip_plan)} zips, "
              f"{synced} mirrored provider column(s), one transaction.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
