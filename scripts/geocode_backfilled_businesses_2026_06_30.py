"""Geocode the 2026-06-30 backfilled businesses that have no coordinates.

The search-audit backfill inserted businesses with real addresses but left
lat/lng NULL (no fabricated coords). This resolves coordinates for those rows
from their stored address using the SAME Google geocoder + Lake-Havasu bounding
-box guard as scripts/regeocode_low_precision_coords.py (an out-of-bounds result
is rejected, never written).

Needs GOOGLE_MAPS_API_KEY only for the actual geocode/--apply. The default
(no key) lists which rows would be geocoded + their addresses, so the selection
is reviewable without touching the paid API.

Usage:
    .venv\\Scripts\\python.exe scripts/geocode_backfilled_businesses_2026_06_30.py            # list rows
    GOOGLE_MAPS_API_KEY=... .venv\\Scripts\\python.exe scripts/geocode_backfilled_businesses_2026_06_30.py --apply --confirm
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# Reuse the proven geocoder + bbox guard (no divergence).
_geo = importlib.import_module("regeocode_low_precision_coords")

BACKFILL_SOURCE = "search_audit_backfill_2026_06_30"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Geocode backfilled businesses (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE lat/lng (needs key)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 74)
    print(f"GEOCODE BACKFILLED BUSINESSES — {'APPLY (writing)' if writing else 'LIST ONLY'}")
    print("=" * 74)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        rows = [
            p for p in db.query(Provider).filter(Provider.source == BACKFILL_SOURCE).all()
            if p.lat is None or p.lng is None
        ]
        print(f"backfilled rows missing coordinates: {len(rows)}")
        for p in rows:
            print(f"  {p.provider_name[:32]:32s} | addr={_geo.usable_address(p) or '(none)'}")
        print()

        if not writing:
            print("LIST ONLY — no geocoding, no writes. Re-run with a key + --apply --confirm.")
            return 0

        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
        if not api_key:
            print("ABORT: GOOGLE_MAPS_API_KEY is not set — cannot geocode.")
            return 1

        import httpx

        written = 0
        with httpx.Client() as client:
            for p in rows:
                addr = _geo.usable_address(p)
                if not addr:
                    print(f"  SKIP {p.provider_name[:30]}: no address")
                    continue
                try:
                    lat, lng = _geo.geocode_address(client, addr, api_key)
                except Exception as exc:  # noqa: BLE001
                    print(f"  FAIL {p.provider_name[:30]}: {exc}")
                    continue
                if not _geo.in_bbox(lat, lng):
                    print(f"  REJECT {p.provider_name[:30]}: {lat},{lng} out of bounds")
                    continue
                print(f"  SET  {p.provider_name[:30]:30s} -> {lat:.5f}, {lng:.5f}")
                p.lat, p.lng = lat, lng
                written += 1
        db.commit()
        print(f"\nAPPLIED: wrote coordinates for {written} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
