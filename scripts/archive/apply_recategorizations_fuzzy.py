"""Resolve the rows ``apply_recategorizations.py`` left UNMATCHED, using a
punctuation-insensitive / containment match.

The exact pass matches an active, non-draft provider only on an exact
(whitespace + case) ``provider_name``. Real display names in the CSV differ from
prod by punctuation ("Elite Martial Arts Inc." vs "Elite Martial Arts, Inc."),
so this companion re-searches the leftover rows with a looser key:

    fuzzy(s) = lowercase, strip every non-alphanumeric run to a single space,
               collapse whitespace.

For each leftover row it ranks candidate providers in two confidence tiers:

  * CONFIDENT = fuzzy-equal, or the CSV name is a substring of the provider name
    (provider is the same or *more* specific). Applied only when exactly one
    distinct provider is confident.
  * LOOSE = the provider name is a substring of the CSV name (provider is
    *less* specific, e.g. a generic "Lake Havasu Golf Club" for an
    "...East Course" row). Never auto-applied — only listed for a human call.

Zero / multiple / loose-only cases are reported and skipped, never guessed.
Rows the exact pass already owns (an exact provider exists) are left alone.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\apply_recategorizations_fuzzy.py --dry-run
    .venv\\Scripts\\python.exe scripts\\apply_recategorizations_fuzzy.py            # apply
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.subcategories import subcategory_by_slug  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

DEFAULT_CSV = _ROOT / "category_recategorizations_2026-06-15.csv"


def _exact(s: str | None) -> str:
    """Mirror apply_recategorizations._norm (whitespace + case only)."""
    return " ".join((s or "").split()).strip().lower()


def _fuzzy(s: str | None) -> str:
    """Lowercase, strip punctuation runs to spaces, collapse whitespace."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()).strip()


def run(*, csv_path: Path, dry_run: bool = True) -> Counter:
    counts: Counter = Counter()
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    db = SessionLocal()
    try:
        providers = (
            db.query(Provider)
            .filter(Provider.is_active.is_(True), Provider.draft.is_(False))
            .all()
        )
        exact_index: dict[str, list[Provider]] = {}
        fuzzy_index: list[tuple[str, Provider]] = []
        for p in providers:
            exact_index.setdefault(_exact(p.provider_name), []).append(p)
            fuzzy_index.append((_fuzzy(p.provider_name), p))

        for row in rows:
            name = (row.get("business") or "").strip()
            target = (row.get("suggested_subcategory") or "").strip()
            if not name or not target:
                continue
            # The exact pass owns any row that already has an exact provider.
            if exact_index.get(_exact(name)):
                continue
            if subcategory_by_slug(target) is None:
                counts["skip_bad_target"] += 1
                print(f"  SKIP (unknown subcategory '{target}'): {name}")
                continue

            fz = _fuzzy(name)
            equal = [p for (k, p) in fuzzy_index if fz and k == fz]
            contains = [p for (k, p) in fuzzy_index if fz and k != fz and fz in k]
            contained = [p for (k, p) in fuzzy_index if k and k != fz and k in fz]

            confident: dict[str, tuple[Provider, str]] = {}
            for p in equal:
                confident.setdefault(p.id, (p, "fuzzy-equal"))
            for p in contains:
                confident.setdefault(p.id, (p, "csv-in-provider"))
            loose = {p.id: p for p in contained if p.id not in confident}

            if len(confident) == 1:
                p, how = next(iter(confident.values()))
                if p.subcategory == target:
                    counts["already_correct"] += 1
                    print(f"  ALREADY OK ({how}): {p.provider_name!r} already {target}")
                    continue
                counts["changed"] += 1
                print(
                    f"  {'WOULD MOVE' if dry_run else 'MOVED'} ({how}): "
                    f"csv {name!r} = prov {p.provider_name!r}: "
                    f"{p.subcategory or '<none>'} -> {target}"
                )
                if not dry_run:
                    p.subcategory = target
            elif len(confident) > 1:
                counts["multi_match"] += 1
                cand = "; ".join(
                    f"{p.provider_name!r}[{p.subcategory or '-'}]" for p, _ in confident.values()
                )
                print(f"  MULTIPLE ({len(confident)}, decide): {name} -> {target} :: {cand}")
            elif loose:
                counts["loose_only"] += 1
                cand = "; ".join(
                    f"{p.provider_name!r}[{p.subcategory or '-'}]" for p in loose.values()
                )
                print(f"  LOOSE-ONLY ({len(loose)}, decide): {name} -> {target} :: {cand}")
            else:
                counts["no_match"] += 1
                print(f"  NO MATCH (decide): {name} -> {target}")

        if not dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would change" if dry_run else "changed"
    print(
        f"\n{verb} {counts['changed']} | already-correct {counts['already_correct']} | "
        f"multiple {counts['multi_match']} | loose-only {counts['loose_only']} | "
        f"no-match {counts['no_match']} | skipped(bad target) {counts['skip_bad_target']}"
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="recategorization CSV path")
    args = parser.parse_args()
    run(csv_path=args.csv, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
