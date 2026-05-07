"""Phase 6 verification report for the LHC business pull.

Queries the providers table for rows where google_place_id IS NOT NULL
(i.e., the businesses sourced from the Google Places pull) and prints the
sanity checks listed in §8 of the execution plan:

  - Total business count + breakdown by ZIP
  - Top 20 google_primary_category values
  - Count of rows with missing website / phone / hours
  - Rating distribution (bucketed histogram + missing count)
  - Review-count distribution (bucketed histogram + missing count)
  - 10 random sample rows for human spot-check

Read-only — no writes.

Usage:
    python -m scripts.places_verify
"""

from __future__ import annotations

import random
from collections import Counter

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

RATING_BUCKETS: list[tuple[str, float, float]] = [
    ("< 3.0", 0.0, 3.0),
    ("3.0 - 4.0", 3.0, 4.0),
    ("4.0 - 4.5", 4.0, 4.5),
    ("4.5+", 4.5, 5.01),
]

REVIEW_BUCKETS: list[tuple[str, int, int | float]] = [
    ("< 10", 0, 10),
    ("10 - 50", 10, 50),
    ("50 - 200", 50, 200),
    ("200 - 1000", 200, 1000),
    ("1000+", 1000, float("inf")),
]


def main() -> None:
    with SessionLocal() as session:
        rows = (
            session.query(Provider)
            .filter(Provider.google_place_id.isnot(None))
            .all()
        )

    print(f"Total Google-sourced providers: {len(rows)}")
    print()

    # ZIP distribution
    zips: Counter[str] = Counter(r.zip or "(none)" for r in rows)
    print("ZIP distribution:")
    for z, c in zips.most_common():
        print(f"  {z}: {c}")
    print()

    # Top primary categories
    primary: Counter[str] = Counter(
        r.google_primary_category or "(none)" for r in rows
    )
    print("Top 20 google_primary_category values:")
    for t, c in primary.most_common(20):
        print(f"  {t}: {c}")
    print()

    # Missing-field counts
    missing_website = sum(1 for r in rows if not r.website)
    missing_phone = sum(1 for r in rows if not r.phone)
    missing_hours = sum(1 for r in rows if not r.google_hours)
    missing_rating = sum(1 for r in rows if r.google_rating is None)
    missing_reviews = sum(1 for r in rows if r.google_review_count is None)
    total = len(rows) or 1
    print("Missing fields:")
    print(f"  website: {missing_website} ({missing_website / total:.0%})")
    print(f"  phone:   {missing_phone} ({missing_phone / total:.0%})")
    print(f"  hours:   {missing_hours} ({missing_hours / total:.0%})")
    print(f"  rating:  {missing_rating} ({missing_rating / total:.0%})")
    print(f"  reviews: {missing_reviews} ({missing_reviews / total:.0%})")
    print()

    # Rating histogram
    print("Rating distribution:")
    for label, lo, hi in RATING_BUCKETS:
        n = sum(1 for r in rows if r.google_rating is not None and lo <= r.google_rating < hi)
        print(f"  {label}: {n}")
    print(f"  no rating: {missing_rating}")
    print()

    # Review-count histogram
    print("Review-count distribution:")
    for label, lo, hi in REVIEW_BUCKETS:
        n = sum(
            1
            for r in rows
            if r.google_review_count is not None and lo <= r.google_review_count < hi
        )
        print(f"  {label}: {n}")
    print(f"  no reviews: {missing_reviews}")
    print()

    # Sample rows
    print("10 random sample rows for spot-check:")
    sample = random.sample(rows, min(10, len(rows)))
    for r in sample:
        rating_str = f"{r.google_rating:.1f}" if r.google_rating is not None else "—"
        reviews_str = (
            f"{r.google_review_count}" if r.google_review_count is not None else "—"
        )
        print(
            f"  {r.provider_name[:40]:40s}  {r.google_primary_category or '—':25s}  "
            f"ZIP {r.zip or '—'}  rating {rating_str}  reviews {reviews_str}"
        )
        print(f"    {r.address or '—'}")


if __name__ == "__main__":
    main()
