"""Fix stale ``primary_category`` on providers recategorized by the 2026-06-15 audit.

``apply_recategorizations.py`` / ``apply_recategorizations_fuzzy.py`` set
``Provider.subcategory`` but NOT ``primary_category``. For cross-primary moves
(e.g. boutiques -> health-medical, attractions -> civic-community) that left a
stale ``primary_category``, so the landing pages route the row by its OLD primary
instead of its NEW subcategory — the Horizon bug, generalized.

This sets ``primary_category = primary_for_subcategory(subcategory)`` for EXACTLY
those recat'd rows whose primary is now stale (non-NULL and disagreeing). Scope is
deliberately tight: a provider qualifies only if it matches a row in
``category_recategorizations_2026-06-15.csv`` by name (exact-normalized, else
punctuation-insensitive containment) AND now carries that row's
``suggested_subcategory``. Every other mis-routed row in prod (pre-existing drift,
possibly an intentional primary or a wrong subcategory — e.g. a movie theater
mis-filed as ``restaurants``) is OUT OF SCOPE and left untouched.

NULL-primary recat rows are already routed correctly (route_provider_filter
tier-2 keys on subcategory when primary is NULL), so they need no change and are
only reported.

Usage (Windows / PowerShell):
    .venv\\Scripts\\python.exe scripts\\fix_recat_stale_primary.py --dry-run
    .venv\\Scripts\\python.exe scripts\\fix_recat_stale_primary.py            # apply
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

from app.categories.subcategories import primary_for_subcategory  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

DEFAULT_CSV = _ROOT / "category_recategorizations_2026-06-15.csv"


def _exact(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def _fuzzy(s: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()).strip()


def _match(name: str, provs: list[Provider]) -> list[Provider]:
    """Providers (already scoped to the target subcategory) matching ``name``."""
    ne = _exact(name)
    exact = [p for p in provs if _exact(p.provider_name) == ne]
    if exact:
        return exact
    nf = _fuzzy(name)
    if not nf:
        return []
    out: dict[str, Provider] = {}
    for p in provs:
        pf = _fuzzy(p.provider_name)
        if pf and (pf == nf or nf in pf or pf in nf):
            out[p.id] = p
    if out:
        return list(out.values())
    # Final tier: every CSV name token present in the provider name (catches an
    # infixed token the substring tiers miss, e.g. "Lake Havasu *AZ* Elks Lodge").
    ctoks = set(nf.split())
    for p in provs:
        if ctoks and ctoks <= set(_fuzzy(p.provider_name).split()):
            out[p.id] = p
    return list(out.values())


def run(*, csv_path: Path, dry_run: bool = True) -> Counter:
    counts: Counter = Counter()
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    db = SessionLocal()
    try:
        for row in rows:
            name = (row.get("business") or "").strip()
            target = (row.get("suggested_subcategory") or "").strip()
            if not name or not target:
                continue
            expected = primary_for_subcategory(target)
            if expected is None:
                continue
            provs = (
                db.query(Provider)
                .filter(
                    Provider.subcategory == target,
                    Provider.is_active.is_(True),
                    Provider.draft.is_(False),
                )
                .all()
            )
            cands = _match(name, provs)
            if len(cands) != 1:
                if cands:
                    counts["ambiguous"] += 1
                    print(f"  AMBIGUOUS ({len(cands)} matches, skipped): {name} [{target}]")
                continue
            p = cands[0]
            if p.primary_category is None:
                counts["null_ok"] += 1
                continue
            if p.primary_category == expected:
                counts["already_correct"] += 1
                continue
            counts["fix"] += 1
            print(
                f"  {'WOULD FIX' if dry_run else 'FIXED'}: {p.provider_name!r} [{target}] "
                f"primary {p.primary_category} -> {expected}"
            )
            if not dry_run:
                p.primary_category = expected
                db.add(p)

        if not dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would fix" if dry_run else "fixed"
    print(
        f"\n{verb} {counts['fix']} stale primaries | already-correct {counts['already_correct']} | "
        f"null-primary (route ok, left) {counts['null_ok']} | ambiguous {counts['ambiguous']}"
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
