"""F3/F4 (askhava audit 2026-06-29) — deactivate a permanently-closed listing and
repoint one wrong outbound link. Dry-run by default; ``--apply`` writes.

Findings (verified read-only against prod + web search 2026-06-29):

F3 — **Havasu Island Golf Course** closed in 2018 (formerly Island Golf Club at the
Nautical Beachfront Resort, ~1000 McCulloch Blvd N). Two active rows still list it
as a live golf course. Action: ``is_active = False`` on both (reversible flag —
not a delete).

F4 — **Bridgewater Links** (source=lhc_golf, id daba6b78) has its website set to the
CVB tourism homepage ``https://golakehavasu.com/`` instead of the course's own site.
Two sibling rows (the 245-review Google Places row + the go_lake_havasu row) already
point at ``https://lakehavasugolf.com/``, corroborating the correct URL. Action:
repoint this row's ``website``.

Lady Lee's Billiards (audit's dead-FB item) has NO stored website/facebook in its
provider row — the rendered FB link comes from a derived source, not this row — so
there is nothing to change here; it's flagged for a separate surface trace.

A before-snapshot is written to the repo root for undo. Run:
    python scripts/fix_f3_f4_closed_and_links.py            # dry-run (counts only)
    python scripts/fix_f3_f4_closed_and_links.py --apply    # write to the configured DB
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# F3: permanently-closed rows to deactivate.
CLOSED_PROVIDER_IDS = (
    "29979a7e-e7dd-49c4-96c5-1a6c35a88a8f",  # Havasu Island Golf Course (admin)
    "5f0c2e32-ae3d-4192-8657-74efd291d516",  # Havasu Island Golf Course (lhc_golf)
)

# F4: (provider_id, expected_current_website, corrected_website)
LINK_FIXES = (
    (
        "daba6b78-c665-416f-a93e-c617ad5b64a5",  # Bridgewater Links (lhc_golf)
        "https://golakehavasu.com/",
        "https://lakehavasugolf.com/",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()
    apply = args.apply

    snapshot: list[dict] = []
    deactivate_count = 0
    link_count = 0

    with SessionLocal() as db:
        # F3 — deactivate closed listings.
        for pid in CLOSED_PROVIDER_IDS:
            p = db.get(Provider, pid)
            if p is None:
                print(f"  F3 SKIP {pid}: not found")
                continue
            snapshot.append(
                {"id": p.id, "name": p.provider_name, "field": "is_active", "before": p.is_active}
            )
            if p.is_active:
                print(f"  F3 deactivate {p.provider_name!r} ({pid})  is_active True -> False")
                deactivate_count += 1
                if apply:
                    p.is_active = False
            else:
                print(f"  F3 already inactive {p.provider_name!r} ({pid})")

        # F4 — repoint wrong outbound link.
        for pid, expect, corrected in LINK_FIXES:
            p = db.get(Provider, pid)
            if p is None:
                print(f"  F4 SKIP {pid}: not found")
                continue
            snapshot.append(
                {"id": p.id, "name": p.provider_name, "field": "website", "before": p.website}
            )
            if (p.website or "").rstrip("/") != expect.rstrip("/"):
                print(
                    f"  F4 WARN {p.provider_name!r} website={p.website!r} != expected {expect!r}; "
                    "skipping to avoid clobbering an unexpected value"
                )
                continue
            print(f"  F4 repoint {p.provider_name!r} ({pid})  {p.website!r} -> {corrected!r}")
            link_count += 1
            if apply:
                p.website = corrected

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = f"f3_f4_fix_snapshot_{stamp}.json"
        with open(snap_path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, default=str)

        print(
            f"\n{'APPLIED' if apply else 'DRY-RUN'}: "
            f"{deactivate_count} deactivation(s), {link_count} link fix(es). "
            f"Snapshot -> {snap_path}"
        )
        if apply:
            db.commit()
            print("Committed.")
        else:
            print("No changes written. Re-run with --apply to commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
