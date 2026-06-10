"""Apply the two TRUE-dupe merges from the 2026-06-03 dupe review (Casey-approved).

Folds each duplicate Google listing into its keeper via the tested
``provider_merge.merge_providers`` primitive (soft-retire + gap-fill; the loser
is kept as a tombstone, never hard-deleted). BRB Market is intentionally NOT
here -- it is two co-located businesses (a convenience store + a gas station),
not a duplicate.

Dry-run by default; pass ``--apply`` to commit.

Usage:
  railway run python scripts/merge_dupe_clusters.py            # dry-run
  railway run python scripts/merge_dupe_clusters.py --apply    # commit
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

from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# (label, keep_id, dup_id) -- keeper first. Keepers chosen by review: the row
# carrying the live Google rating/review history.
MERGES = [
    (
        "Jin's Massage",
        "1ba6dca7-3f44-4840-8011-848e6c592942",  # keep: jin-s-massage (115 reviews)
        "4dace698-d68c-41a1-bb76-c15c77cbbd96",  # dup:  jin-s-massage-2 (2 reviews, stale listing)
    ),
    (
        "SUGARED IN THE CITY LLC",
        "1218152f-ad53-4bd0-bd91-2c569616c421",  # keep: sugared-in-the-city-llc (has rating)
        "2c8b7089-9487-4a9d-aaed-cfabfadbea79",  # dup:  sugared-in-the-city-llc-2
    ),
]


def run(apply: bool) -> int:
    db = SessionLocal()
    try:
        for label, keep_id, dup_id in MERGES:
            print(f"\n=== {label} ===")
            res = merge_providers(db, keep_id=keep_id, dup_id=dup_id, dry_run=not apply)
            print(f"  keep={res.keep_id}  retire={res.dup_id}")
            print(f"  gap_filled={res.gap_filled or '(none)'}")
            print(f"  repointed={res.repointed or '(none)'}")
            print(f"  combined_source={res.combined_source!r}")
            if apply:
                db.commit()
                # Verify post-state from the DB.
                dup = db.get(Provider, dup_id)
                keep = db.get(Provider, keep_id)
                print(
                    f"  POST: keep active={keep.is_active} draft={keep.draft} | "
                    f"dup active={dup.is_active} draft={dup.draft} pending={dup.pending_review}"
                )
        if not apply:
            print("\n[dry-run] no writes. Re-run with --apply to commit.")
        else:
            print("\nAPPLIED + committed.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run(apply="--apply" in sys.argv[1:]))
