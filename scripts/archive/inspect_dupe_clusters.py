"""Read-only inspection of the 3 dupe clusters from report_provider_dupes.py.

Dumps each provider's identity/provenance/completeness + inbound reference
counts, and runs a DRY-RUN merge for the two true-dupe clusters so an admin can
see the proposed keeper, gap-fill, and repoint blast radius before approving a
real merge. NO writes (dry_run=True; the session is rolled back).

Usage (prod env):  railway run python scripts/inspect_dupe_clusters.py
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
from app.db.models import (  # noqa: E402
    AnalyticsEvent,
    Claim,
    Contribution,
    Event,
    PeerRecommendation,
    Photo,
    Program,
    Provider,
    UserFavorite,
)

# (label, [keep_id, dup_id]) — order is the PROPOSED keeper first. None merge for
# BRB (likely miscategorization, not a dupe).
CLUSTERS = {
    "Jin's Massage": [
        "1ba6dca7-3f44-4840-8011-848e6c592942",  # jin-s-massage
        "4dace698-d68c-41a1-bb76-c15c77cbbd96",  # jin-s-massage-2
    ],
    "SUGARED IN THE CITY LLC": [
        "1218152f-ad53-4bd0-bd91-2c569616c421",  # sugared-in-the-city-llc
        "2c8b7089-9487-4a9d-aaed-cfabfadbea79",  # sugared-in-the-city-llc-2
    ],
    "BRB Market": [
        "957d9f69-08ce-4c82-8223-64cb41baede9",  # brb-market food_drink
        "a512a220-d5fd-4a42-8a12-edf33e93eeb8",  # brb-market-2 auto
    ],
}

_SCALAR = (
    "phone", "email", "website", "facebook", "hours", "description",
    "lat", "lng", "google_place_id", "google_rating", "google_review_count",
    "google_primary_category", "subcategory", "category_id", "district", "zip",
)


def _count(db, model, attr, value) -> int:
    from sqlalchemy import func, select
    col = getattr(model, attr)
    return int(db.scalar(select(func.count()).select_from(model).where(col == value)) or 0)


def _inbound(db, p: Provider) -> dict[str, int]:
    out: dict[str, int] = {}
    for model, attr in [
        (Event, "provider_id"), (Program, "provider_id"),
        (Contribution, "created_provider_id"), (AnalyticsEvent, "provider_id"),
    ]:
        n = _count(db, model, attr, p.id)
        if n:
            out[f"{model.__tablename__}.{attr}"] = n
    for model, attr in [
        (Event, "entity_id"), (Program, "entity_id"), (Photo, "entity_id"),
        (PeerRecommendation, "entity_id"), (UserFavorite, "entity_id"),
        (Claim, "entity_id"),
    ]:
        n = _count(db, model, attr, p.entity_id)
        if n:
            out[f"{model.__tablename__}.{attr}"] = n
    return out


def _dump(db, p: Provider, role: str) -> None:
    populated = [f for f in _SCALAR if getattr(p, f, None) not in (None, "", [], {})]
    print(f"  [{role}] {p.provider_name!r}  slug={p.slug}")
    print(f"        id={p.id}")
    print(f"        category={p.category!r}  subcategory={p.subcategory!r}  category_id={p.category_id}")
    print(f"        source={p.source!r}  verified={p.verified}  tier={p.tier}  draft={p.draft}  active={p.is_active}")
    print(f"        created={p.created_at}  updated={p.updated_at}")
    print(f"        verification_method={p.verification_method!r}  last_verified_at={p.last_verified_at}")
    print(f"        populated fields ({len(populated)}): {', '.join(populated)}")
    inbound = _inbound(db, p)
    print(f"        inbound refs: {inbound or '(none)'}")


def run() -> None:
    db = SessionLocal()
    try:
        for label, (keep_id, dup_id) in CLUSTERS.items():
            print(f"\n{'=' * 72}\nCLUSTER: {label}\n{'=' * 72}")
            keep = db.get(Provider, keep_id)
            dup = db.get(Provider, dup_id)
            if keep is None or dup is None:
                print(f"  !! missing row(s): keep={keep is not None} dup={dup is not None}")
                continue
            _dump(db, keep, "proposed KEEP")
            _dump(db, dup, "proposed DUP ")

            if label == "BRB Market":
                print("\n  -> NOT merging: one row is food_drink, one is auto. Likely a")
                print("     miscategorization of the SAME business, not two businesses.")
                print("     Decide correct category, fix the wrong row; do not merge blindly.")
                continue

            print("\n  -- DRY-RUN merge (keep <- dup), no writes --")
            try:
                res = merge_providers(db, keep_id=keep_id, dup_id=dup_id, dry_run=True)
                print(f"     keeper:     {res.keep_id}")
                print(f"     retire:     {res.dup_id}")
                print(f"     gap_filled: {res.gap_filled or '(nothing — keeper already complete)'}")
                print(f"     repointed:  {res.repointed or '(no inbound refs to move)'}")
                print(f"     combined_source: {res.combined_source!r}")
            except ValueError as exc:
                print(f"     merge refused: {exc}")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    run()
