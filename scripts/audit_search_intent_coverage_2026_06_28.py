"""Read-only probe: run the audit's §11 "failing" search queries through the LIVE
search path and report which actually return 0 provider results today.

The audit (2026-06-27) listed ~80 intent queries as "No matches". But several of
its other claims proved stale this session, so this verifies empirically: each
query is run through `app.search.routes._keyword_provider_rows` (the exact path
behind GET /search) against prod, and we print the hit count. Zero-hit queries are
the REAL gaps to wire; non-zero ones already work.

READ-ONLY. SELECT-only.

    .venv\\Scripts\\python.exe scripts/audit_search_intent_coverage_2026_06_28.py
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
from app.search.routes import _keyword_provider_rows  # noqa: E402

_QUERIES: dict[str, tuple[str, ...]] = {
    "Marine": (
        "fix my boat", "boat mechanic", "buy a boat", "used boats",
        "marine supply", "boat parts", "where do I put my boat",
    ),
    "Pools": (
        "full supply", "pool supply", "pool store", "pool chemicals",
        "pool builder", "build a pool", "hot tub repair", "pool pump",
    ),
    "HVAC": (
        "AC repair", "air conditioning repair", "my AC broke", "fix my air conditioner",
        "ac install", "new ac unit", "furnace repair", "heating repair", "mini split",
        "ac tune up", "it's too hot in my house", "swamp cooler", "swamp cooler repair",
        "evaporative cooler",
    ),
    "Housing": (
        "fix my toilet", "water heater", "roofer", "leaky roof", "exterminator",
        "bug guy", "lawn care", "yard work", "tree trimming", "maid service",
        "security system", "painter", "junk removal", "pressure washing",
        "water softener", "window install",
    ),
    "Retail": ("where to buy a gift", "flowers", "gift shop"),
    "Health": (
        "emergency room", "urgent care", "hearing aids", "assisted living",
        "senior care", "nursing home", "in-home care", "hospice", "dialysis",
        "dermatologist", "pediatrician", "emergency vet",
    ),
    "Professional": (
        "DMV", "real estate agent", "tax preparer", "title company", "printing",
        "high school", "water company", "electric company", "trash pickup", "recycling",
    ),
    "LodgingToDo": (
        "airbnb", "vacation rental", "side by side rental", "OHV", "live music",
        "nightlife", "bike rental",
    ),
}


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print("SEARCH INTENT COVERAGE PROBE (live /search path)  — READ-ONLY")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    zero: list[str] = []
    total = 0
    with SessionLocal() as db:
        for cluster, qs in _QUERIES.items():
            print(f"--- {cluster} ---")
            for q in qs:
                total += 1
                try:
                    rows = _keyword_provider_rows(db, q_clean=q, limit=50)
                    n = len(rows)
                except Exception as exc:  # noqa: BLE001
                    print(f"   ERR  {q!r}: {type(exc).__name__}")
                    continue
                flag = "ZERO" if n == 0 else f"{n:>3d} "
                if n == 0:
                    zero.append(f"{cluster}: {q}")
                top = rows[0].provider_name[:30] if rows else ""
                print(f"   [{flag}] {q:32s} {top}")
            print()
    print("=" * 78)
    print(f"queries: {total}   ZERO-hit (real gaps): {len(zero)}")
    for z in zero:
        print(f"   GAP  {z}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
