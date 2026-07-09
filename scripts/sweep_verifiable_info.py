"""§6.9 GLOBAL RULE — no dead listings. Flag (and optionally soft-hide) active
providers that carry NO verifiable information at all.

"Verifiable info" = at least one of: a website, a Google Business link
(``google_place_id``), a phone number, or a street address. A real business is
allowed to lack a website — but a listing a user can click into that shows
*nothing* (no site, no Google entry, no phone, no address) is a dead end and
must not stay live.

Gate (CLAUDE.md): READ-ONLY by default. It prints counts and writes a review CSV
of every candidate; it writes to the DB **only** with ``--apply``, and when it
does it (a) soft-hides via ``is_active=False`` (never deletes) and (b) writes a
JSON undo snapshot of the affected ids so the change is reversible.

Run from repo root with the prod venv:
    .venv\\Scripts\\python.exe scripts\\sweep_verifiable_info.py            # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\sweep_verifiable_info.py --apply     # soft-hide + snapshot

Options:
    --require-active-only/--include-inactive   default: only scan is_active rows
    --out PATH                                  CSV path (default: timestamped)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def _has_verifiable_info(p: Provider) -> bool:
    """True if the listing exposes at least one piece of clickable/verifiable
    information. Kept deliberately permissive — a single real signal is enough."""
    website = (p.website or "").strip()
    google = (p.google_place_id or "").strip()
    phone = (p.phone or "").strip()
    address = (p.address or "").strip()
    # facebook is a real, clickable signal too.
    facebook = (p.facebook or "").strip()
    return bool(website or google or phone or address or facebook)


def _utcstamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="soft-hide flagged rows (default: dry-run, no writes)")
    ap.add_argument("--include-inactive", action="store_true",
                    help="also scan rows already is_active=False (default: active only)")
    ap.add_argument("--out", default=None, help="review CSV path")
    args = ap.parse_args()

    stamp = _utcstamp()
    out_csv = args.out or f"verifiable_info_flagged_{stamp}.csv"

    db = SessionLocal()
    try:
        stmt = select(Provider)
        if not args.include_inactive:
            stmt = stmt.where(Provider.is_active.is_(True))
        rows = list(db.scalars(stmt))

        flagged = [p for p in rows if not _has_verifiable_info(p)]

        print(f"Scanned {len(rows)} provider rows "
              f"({'active only' if not args.include_inactive else 'all'}).")
        print(f"Flagged {len(flagged)} with NO verifiable info "
              f"(no website / google / phone / address / facebook).")

        # Always write the review CSV — this is what Casey eyeballs before --apply.
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "provider_name", "category", "primary_category",
                        "source", "is_active", "created_at"])
            for p in flagged:
                w.writerow([p.id, p.provider_name, p.category, p.primary_category,
                            p.source, p.is_active, p.created_at])
        print(f"Wrote review CSV: {out_csv}")

        if not flagged:
            print("Nothing to do.")
            return 0

        if not args.apply:
            print(f"\nDRY-RUN: would set is_active=False on {len(flagged)} rows. "
                  "Review the CSV, then re-run with --apply.")
            return 0

        snapshot = {
            "script": "sweep_verifiable_info",
            "applied_at": stamp,
            "rule": "no website/google/phone/address/facebook",
            "soft_hidden_ids": [p.id for p in flagged],
        }
        snap_path = f"verifiable_info_snapshot_{stamp}.json"
        with open(snap_path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)

        for p in flagged:
            p.is_active = False
        db.commit()
        print(f"\nAPPLIED: soft-hid {len(flagged)} rows. Undo snapshot: {snap_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
