"""§6.8 GLOBAL RULE — Lake Havasu only. Flag (and optionally soft-hide) active
providers that are clearly NOT local to Lake Havasu City.

A row is flagged as a non-local CANDIDATE when there is a positive signal it
lives somewhere else — never merely because data is missing (empty rows are the
job of sweep_verifiable_info.py). Signals, any of which flags the row:

  * ``zip`` is present and is not a Lake Havasu City zip, OR
  * the address contains another town's name (Parker, Bullhead City, Kingman,
    Needles, Quartzsite, …), OR
  * ``lat``/``lng`` are present and the point is > RADIUS_MI from the LHC center.

Allowlist: Havasu Landing Resort & Casino sits across the channel in Havasu
Lake, CA (zip 92363) but is, by Casey's explicit call, the local casino — its
name is exempted so the zip/coord rules never flag it. Add more exemptions to
``ALLOW_NAME_SUBSTRINGS`` as needed.

Gate (CLAUDE.md): READ-ONLY by default — prints counts and writes a review CSV.
Writes to the DB **only** with ``--apply``, soft-hiding via ``is_active=False``
(never deletes) and writing a JSON undo snapshot of the affected ids.

This sweep FLAGS for human review; the CSV is meant to be eyeballed before
--apply, because address/zip data is imperfect and a few in-town rows may carry
a wrong zip. Tune RADIUS_MI / token lists from what the dry-run surfaces.

Run from repo root with the prod venv:
    .venv\\Scripts\\python.exe scripts\\sweep_locality.py            # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\sweep_locality.py --apply     # soft-hide + snapshot
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

from sqlalchemy import select

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# Lake Havasu City reference. Zips include the PO-box range (86405); all count as
# local. Center is the McCulloch/uptown area; RADIUS_MI generously covers the
# whole incorporated city + immediate fringe.
LHC_ZIPS = {"86403", "86404", "86405", "86406"}
LHC_LAT, LHC_LNG = 34.4839, -114.3224
RADIUS_MI = 20.0

# Address tokens that name another town => strong non-local signal.
OTHER_TOWN_TOKENS = (
    "parker", "bullhead", "kingman", "needles", "quartzsite", "bouse", "wikieup",
    "topock", "golden valley", "fort mohave", "mohave valley", "yuma", "phoenix",
    "las vegas", "henderson", "laughlin", "prescott", "wickenburg", "scottsdale",
    "tempe", "mesa", "chandler", "flagstaff", "blythe", "salome",
)

# Name substrings that are LOCAL exceptions despite a non-LHC zip/coord.
ALLOW_NAME_SUBSTRINGS = ("havasu landing",)


def _haversine_mi(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.7613  # earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _flag_reason(p: Provider, radius: float, use_distance: bool) -> str | None:
    """Return a short reason string if the row looks non-local, else None.

    Precision-first: a confirmed Lake Havasu City zip is trusted as LOCAL and
    short-circuits, because coordinates on many ``go_lake_havasu`` rows are
    garbage (sentinel ~1107mi distances on businesses plainly in town). We flag
    only on a *real* non-LHC zip or an explicit other-town name. Distance is
    opt-in (``--use-distance``) for a manual review pass, never the default."""
    name = (p.provider_name or "").lower()
    if any(s in name for s in ALLOW_NAME_SUBSTRINGS):
        return None

    zip_ = (p.zip or "").strip()[:5]
    if zip_:
        if zip_ in LHC_ZIPS:
            return None  # confirmed local zip — trust it over coordinates
        return f"zip={zip_}"

    # No zip: fall back to an explicit other-town name in the address.
    addr = (p.address or "").lower()
    for tok in OTHER_TOWN_TOKENS:
        if tok in addr:
            return f"town:{tok}"

    if use_distance and p.lat is not None and p.lng is not None:
        d = _haversine_mi(LHC_LAT, LHC_LNG, p.lat, p.lng)
        if d > radius:
            return f"dist={d:.0f}mi"

    return None


def _utcstamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="soft-hide flagged rows (default: dry-run, no writes)")
    ap.add_argument("--include-inactive", action="store_true",
                    help="also scan rows already is_active=False (default: active only)")
    ap.add_argument("--radius", type=float, default=RADIUS_MI,
                    help=f"distance flag threshold in miles (default {RADIUS_MI})")
    ap.add_argument("--use-distance", action="store_true",
                    help="ALSO flag by coordinate distance (OFF by default: coords are "
                         "unreliable in this dataset and produce false positives)")
    ap.add_argument("--out", default=None, help="review CSV path")
    args = ap.parse_args()
    radius = args.radius

    stamp = _utcstamp()
    out_csv = args.out or f"locality_flagged_{stamp}.csv"

    db = SessionLocal()
    try:
        stmt = select(Provider)
        if not args.include_inactive:
            stmt = stmt.where(Provider.is_active.is_(True))
        rows = list(db.scalars(stmt))

        flagged: list[tuple[Provider, str]] = []
        for p in rows:
            reason = _flag_reason(p, radius, args.use_distance)
            if reason:
                flagged.append((p, reason))

        print(f"Scanned {len(rows)} provider rows "
              f"({'active only' if not args.include_inactive else 'all'}); "
              f"radius={radius}mi.")
        print(f"Flagged {len(flagged)} as likely NON-LOCAL (review before apply).")

        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "provider_name", "reason", "zip", "address",
                        "category", "source", "is_active"])
            for p, reason in flagged:
                w.writerow([p.id, p.provider_name, reason, p.zip, p.address,
                            p.category, p.source, p.is_active])
        print(f"Wrote review CSV: {out_csv}")

        if not flagged:
            print("Nothing to do.")
            return 0

        if not args.apply:
            print(f"\nDRY-RUN: would set is_active=False on {len(flagged)} rows. "
                  "Review the CSV, then re-run with --apply.")
            return 0

        snapshot = {
            "script": "sweep_locality",
            "applied_at": stamp,
            "radius_mi": radius,
            "soft_hidden": [{"id": p.id, "reason": r} for p, r in flagged],
        }
        snap_path = f"locality_snapshot_{stamp}.json"
        with open(snap_path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)

        for p, _ in flagged:
            p.is_active = False
        db.commit()
        print(f"\nAPPLIED: soft-hid {len(flagged)} rows. Undo snapshot: {snap_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
