"""Diagnose the 532 providers whose google_photo_refs are non-null but
the photo backfill skipped them as not-convertible.

Run via:
    railway run python -m scripts.inspect_unresolved_photo_refs

Prints summary stats + up to 20 sample rows so we can decide whether
to extend the resolver, null the field out, or just leave them.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def main() -> None:
    type_counts: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()
    samples: list[dict] = []

    with SessionLocal() as db:
        stmt = (
            select(Provider)
            .where(Provider.google_photo_refs.isnot(None))
            .where(Provider.google_photo_urls.is_(None))
        )
        rows = list(db.execute(stmt).scalars().all())
        print(f"Total leftover: {len(rows)}")

        for p in rows:
            refs = p.google_photo_refs
            type_name = type(refs).__name__

            if isinstance(refs, list):
                if not refs:
                    pattern = "empty-list"
                else:
                    first = refs[0]
                    if not isinstance(first, str):
                        pattern = f"list-of-{type(first).__name__}"
                    elif first.startswith("http://") or first.startswith("https://"):
                        pattern = "list-of-full-urls"
                    elif first.startswith("places/"):
                        pattern = "list-of-places-refs"
                    else:
                        pattern = f"list-of-other-string ({first[:40]!r})"
            elif isinstance(refs, str):
                if refs.startswith("http"):
                    pattern = "bare-string-url"
                elif refs.startswith("places/"):
                    pattern = "bare-string-places-ref"
                else:
                    pattern = f"bare-string-other ({refs[:40]!r})"
            elif isinstance(refs, dict):
                pattern = f"dict (keys={sorted(refs.keys())[:5]!r})"
            else:
                pattern = f"other-{type_name}"

            type_counts[type_name] += 1
            pattern_counts[pattern] += 1

            if len(samples) < 20:
                samples.append(
                    {
                        "slug": p.slug,
                        "type": type_name,
                        "pattern": pattern,
                        "value": (json.dumps(refs)[:200] if refs is not None else None),
                    }
                )

    print("\n--- python type breakdown ---")
    for t, n in type_counts.most_common():
        print(f"  {n:4d}  {t}")

    print("\n--- pattern breakdown ---")
    for p, n in pattern_counts.most_common():
        print(f"  {n:4d}  {p}")

    print("\n--- 20 samples ---")
    for s in samples:
        print(f"  slug={s['slug']!r:40s} pattern={s['pattern']!r:30s} value={s['value']}")


if __name__ == "__main__":
    main()
