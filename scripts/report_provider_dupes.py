"""Read-only report of LIKELY-TRUE duplicate providers (C-4). NO writes.

The naive "same name" clustering over-reports chains — Starbucks×5 is five real
locations, not a duplicate. True duplicates share an identity: the same Google
``place_id``, OR the same name AND the same street number. This script surfaces
only those, so an admin reviews real dupes (and merges via the existing
``app/contrib/provider_merge`` tooling) instead of a wall of chains.

Usage (with prod env):  railway run python scripts/report_provider_dupes.py
"""

from __future__ import annotations

import csv
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

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_REPORT_PATH = _ROOT / "provider_dupes_report.csv"


def _norm_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _street_number(address: str | None) -> str | None:
    m = re.match(r"\s*(\d+)\b", address or "")
    return m.group(1) if m else None


def run() -> None:
    db = SessionLocal()
    rows_out: list[dict[str, str]] = []
    try:
        providers = db.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        ).all()

        # 1. Same google_place_id = same physical place = true duplicate.
        by_place: dict[str, list[Provider]] = defaultdict(list)
        for p in providers:
            pid = (getattr(p, "google_place_id", None) or "").strip()
            if pid:
                by_place[pid].append(p)
        place_dupes = {k: v for k, v in by_place.items() if len(v) > 1}

        # 2. Same normalized name AND same street number, but NOT already caught
        #    by place_id — distinguishes a true dupe from a chain (chains share a
        #    name but have different street numbers).
        seen_ids = {p.id for grp in place_dupes.values() for p in grp}
        by_name_addr: dict[tuple[str, str], list[Provider]] = defaultdict(list)
        for p in providers:
            if p.id in seen_ids:
                continue
            num = _street_number(p.address)
            nm = _norm_name(p.provider_name)
            if nm and num:
                by_name_addr[(nm, num)].append(p)
        name_addr_dupes = {k: v for k, v in by_name_addr.items() if len(v) > 1}

        print("\n=== PROVIDER DUPLICATES (read-only) ===")
        print(f"  active providers scanned:           {len(providers)}")
        print(f"  same-place_id clusters (true dupes): {len(place_dupes)}")
        print(f"  same name+street# clusters:          {len(name_addr_dupes)}")

        print("\n  -- same google_place_id (highest confidence) --")
        for pid, grp in sorted(place_dupes.items(), key=lambda kv: -len(kv[1]))[:25]:
            print(f"    {len(grp)}x  {grp[0].provider_name!r}  (place_id {pid[:18]}…)")
            for p in grp:
                rows_out.append(
                    {
                        "cluster_type": "place_id",
                        "key": pid,
                        "id": p.id,
                        "name": p.provider_name or "",
                        "slug": p.slug or "",
                        "category": p.category or "",
                        "address": (p.address or "")[:120],
                    }
                )

        print("\n  -- same name + street number (no shared place_id) --")
        for (nm, num), grp in sorted(name_addr_dupes.items(), key=lambda kv: -len(kv[1]))[:25]:
            print(f"    {len(grp)}x  {grp[0].provider_name!r}  (#{num})")
            for p in grp:
                rows_out.append(
                    {
                        "cluster_type": "name+street",
                        "key": f"{nm}|{num}",
                        "id": p.id,
                        "name": p.provider_name or "",
                        "slug": p.slug or "",
                        "category": p.category or "",
                        "address": (p.address or "")[:120],
                    }
                )
    finally:
        db.close()

    with _REPORT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["cluster_type", "key", "id", "name", "slug", "category", "address"],
        )
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"\n  CSV written: {_REPORT_PATH}")
    print("  Review, then merge true dupes via the admin provider-merge tooling (gated).")


if __name__ == "__main__":
    run()
