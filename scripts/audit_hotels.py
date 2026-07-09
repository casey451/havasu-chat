"""§6.3 Hotels & Motels audit. Every listing in the "hotels" subcategory must
(a) actually be a hotel/motel/resort and (b) have a website. Soft-hide anything
that fails either test.

The hotels subcategory is polluted with vacation rentals and property-management
companies ("2 Mi to Lake Havasu... Home", "Adventure Vacation Rentals", "Empty
Spaces Vacation Rental Management", luxury villas, etc.). Removal logic:

  * REMOVE if the name looks like a vacation rental / property manager
    (VR_TOKENS) AND it does not carry a real-lodging word (REAL_TOKENS). The
    real-lodging guard protects genuine hotels/resorts (London Bridge Resort,
    The Nautical Beachfront Resort, Islander Resort, etc.).
  * REMOVE if it has no website (brief rule b), unless it carries a real-lodging
    word — those are flagged "no-website" but a few may be genuine websiteless
    motels worth restoring + adding a site.
  * KEEP everything else.

Two known mislabels (a bar, a restaurant) are NOT hidden here — they're real
businesses in the wrong subcategory and are reported for recategorization.

Gate (CLAUDE.md): READ-ONLY by default. Writes only with ``--apply`` (soft-hide,
never delete) + a JSON undo snapshot + a review CSV.

    .venv\\Scripts\\python.exe scripts\\audit_hotels.py            # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\audit_hotels.py --apply     # soft-hide + snapshot
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# Strong "this is real lodging" signals — protect these from the VR heuristic.
# NOTE: "resort" is deliberately NOT here — real resorts (London Bridge Resort,
# The Nautical, Islander) don't match any VR token so they stay KEPT anyway,
# while "The Sands Vacation Resort" / "Desert Resort Properties" should be caught.
REAL_TOKENS = ("hotel", "motel", " inn", "inn ", "suites", "lodge")
# Vacation-rental / property-manager / individual-home signals.
VR_TOKENS = (
    "vacation rental", "vacation rentals", "rental cleaning", "rentals & sales",
    "rentals and sales", "property management", "properties", "getaway", " mi to ",
    "home w/", "holiday home", "luxury home", "luxury villa", "villa w", "poolside",
    "- bbq", "vacation resort", ": home", "~ ", "boat parking", "pet-friendly home",
    "minutes from", "close to downtown",
)
# Known mislabels that are real businesses in the wrong subcategory (reported,
# not hidden).
RECATEGORIZE_NOTE = ("HEAT Bar", "Turtle Grille")


def _classify(p: Provider) -> tuple[str, str]:
    """Return (action, reason) where action in {keep, remove, recat}."""
    name = (p.provider_name or "")
    name_l = name.lower()
    has_site = bool((p.website or "").strip())
    is_real = any(t in name_l for t in REAL_TOKENS)
    looks_vr = any(t in name_l for t in VR_TOKENS)

    if any(m.lower() in name_l for m in RECATEGORIZE_NOTE):
        return "recat", "not a hotel (bar/restaurant) — recategorize, do not hide"
    if looks_vr and not is_real:
        return "remove", "vacation-rental / not-a-hotel"
    if not has_site and not is_real:
        return "remove", "no-website + not clearly real lodging"
    if not has_site:
        return "remove", "no-website (brief 6.3b) — real-lodging name, restore w/ site if legit"
    return "keep", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="soft-hide flagged rows (default: dry-run)")
    args = ap.parse_args()

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(Provider).where(
            Provider.subcategory == "hotels", Provider.is_active.is_(True))
            .order_by(Provider.provider_name)))

        remove, keep, recat = [], [], []
        for p in rows:
            action, reason = _classify(p)
            (remove if action == "remove" else recat if action == "recat" else keep).append((p, reason))

        print(f"hotels: {len(rows)} active -> keep {len(keep)}, remove {len(remove)}, "
              f"recategorize {len(recat)}\n")
        print("REMOVE (soft-hide):")
        for p, r in remove:
            print(f"  {p.provider_name}  [{r}]")
        print("\nRECATEGORIZE (not hidden, reported):")
        for p, r in recat:
            print(f"  {p.provider_name}")
        print("\nKEEP (real hotels):")
        for p, _ in keep:
            print(f"  {p.provider_name}")

        out_csv = f"hotels_audit_{stamp}.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["action", "provider_name", "reason", "website", "id"])
            for p, r in remove:
                w.writerow(["remove", p.provider_name, r, p.website, p.id])
            for p, r in recat:
                w.writerow(["recat", p.provider_name, r, p.website, p.id])
            for p, _ in keep:
                w.writerow(["keep", p.provider_name, "", p.website, p.id])
        print(f"\nWrote {out_csv}")

        if not remove:
            print("Nothing to hide.")
            return 0
        if not args.apply:
            print(f"\nDRY-RUN: would soft-hide {len(remove)} rows. Review CSV, re-run with --apply.")
            return 0

        snap = {"script": "audit_hotels", "applied_at": stamp,
                "soft_hidden": [{"id": p.id, "name": p.provider_name, "reason": r} for p, r in remove]}
        with open(f"hotels_audit_snapshot_{stamp}.json", "w", encoding="utf-8") as fh:
            json.dump(snap, fh, indent=2)
        for p, _ in remove:
            p.is_active = False
        db.commit()
        print(f"\nAPPLIED: soft-hid {len(remove)} rows. Snapshot: hotels_audit_snapshot_{stamp}.json")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
