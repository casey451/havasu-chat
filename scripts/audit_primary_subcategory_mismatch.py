"""READ-ONLY audit of providers whose ``primary_category`` disagrees with the
canonical primary for their ``subcategory`` (2026-06-15 coverage-audit follow-up).

Why this matters
----------------
``route_provider_filter`` (app/categories/queries.py) treats a non-NULL
``primary_category`` as the authoritative tier-1 signal. The
``/lake-havasu/{subcategory}`` landings, by contrast, filter on ``subcategory``.
So when a provider's ``primary_category`` points at category A but its
``subcategory`` canonically belongs to category B, the row mis-routes: it shows
up on A's pages and is invisible on B's subcategory landing (or vice-versa).

Root cause for a chunk of these: the 2026-06-15 recat scripts
(``apply_recategorizations.py`` / ``apply_recategorizations_fuzzy.py``) set
``Provider.subcategory`` but NOT ``primary_category``. Any *cross-primary* recat
(e.g. CVS boutiques->health-medical) therefore left a stale primary behind.

This script ONLY reads. It classifies every mismatch into three buckets:

  * ``stale_recat`` — SAFE auto-fix. The row's current ``subcategory`` matches a
    row in the recat CSV (exact or punctuation-insensitive) AND the current
    ``primary_category`` equals the primary the *old* subcategory mapped to.
    That is the exact fingerprint of "recat moved subcategory, left primary
    stale", so ``primary_category = primary_for_subcategory(subcategory)`` is
    provably the correction.
  * ``review`` — subcategory maps to a real primary that differs from the
    current one, but the mismatch is NOT explained by the recat CSV. Plausibly
    an intentional cross-listing or deliberate resort primary (e.g. Havasu
    Landing Resort & Casino subcat=parks-beaches primary=lodging). Needs a human
    eyeball before any change.
  * ``no_target`` — ``subcategory`` is NULL or maps to nothing, so
    ``primary_for_subcategory`` returns ``None``. The "safe fix" rule cannot
    apply here (it would null out the primary). Listed for completeness; never
    auto-fixed.

Usage (Windows / PowerShell)::

    .venv\\Scripts\\python.exe scripts\\audit_primary_subcategory_mismatch.py
    .venv\\Scripts\\python.exe scripts\\audit_primary_subcategory_mismatch.py --out audit.csv

``--out`` writes the full row-level detail to a CSV; without it, only the console
summary prints. There is intentionally NO write/apply path in this file.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.subcategories import primary_for_subcategory  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import Provider  # noqa: E402

DEFAULT_RECAT_CSV = _ROOT / "category_recategorizations_2026-06-15.csv"


def _exact(s: str | None) -> str:
    """Whitespace + case normalization (mirrors apply_recategorizations._norm)."""
    return " ".join((s or "").split()).strip().lower()


def _fuzzy(s: str | None) -> str:
    """Lowercase, punctuation runs -> single space, collapse whitespace.

    Mirrors apply_recategorizations_fuzzy._fuzzy so a CSV name matched fuzzily by
    the recat pass is matched the same way here.
    """
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()).strip()


@dataclass(frozen=True)
class RecatRow:
    business: str
    current_subcategory: str
    suggested_subcategory: str
    confidence: str
    notes: str


def load_recat_rows(csv_path: Path) -> list[RecatRow]:
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8") as fh:
        out = []
        for row in csv.DictReader(fh):
            out.append(
                RecatRow(
                    business=(row.get("business") or "").strip(),
                    current_subcategory=(row.get("current_subcategory") or "").strip(),
                    suggested_subcategory=(row.get("suggested_subcategory") or "").strip(),
                    confidence=(row.get("confidence") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return out


@dataclass
class MismatchRow:
    provider_id: int
    provider_name: str
    subcategory: str | None
    current_primary: str | None
    expected_primary: str | None
    bucket: str
    recat_match: str  # "" | "exact" | "fuzzy"
    recat_notes: str


def classify(db, recat_rows: list[RecatRow]) -> list[MismatchRow]:
    """Return one MismatchRow per active, non-draft, *classified* provider whose
    ``primary_category`` != ``primary_for_subcategory(subcategory)``.

    "classified" == ``primary_category IS NOT NULL`` (matches the audit framing).
    """
    # Index recat CSV rows by exact + fuzzy name. A provider qualifies for the
    # stale_recat bucket only when (a) its current subcategory == the CSV
    # suggested subcategory (i.e. the recat actually landed on it) and (b) its
    # current primary == the primary the OLD subcategory mapped to (the exact
    # fingerprint of a stale-primary left by a cross-primary recat).
    exact_index: dict[str, list[RecatRow]] = defaultdict(list)
    fuzzy_index: dict[str, list[RecatRow]] = defaultdict(list)
    for r in recat_rows:
        exact_index[_exact(r.business)].append(r)
        fuzzy_index[_fuzzy(r.business)].append(r)

    providers = (
        db.query(Provider)
        .filter(
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
            Provider.primary_category.isnot(None),
        )
        .all()
    )

    out: list[MismatchRow] = []
    for p in providers:
        expected = primary_for_subcategory(p.subcategory)
        current = p.primary_category
        if current == expected:
            continue  # in agreement — not a mismatch

        recat_match = ""
        recat_notes = ""
        bucket: str

        if expected is None:
            # subcategory NULL or unmapped -> "safe fix" rule can't apply.
            bucket = "no_target"
        else:
            # Does the recat CSV explain this exact stale primary?
            candidates = exact_index.get(_exact(p.provider_name))
            how = "exact"
            if not candidates:
                candidates = fuzzy_index.get(_fuzzy(p.provider_name))
                how = "fuzzy"
            matched = None
            if candidates:
                for r in candidates:
                    if not r.suggested_subcategory or not r.current_subcategory:
                        continue
                    # (a) the recat landed: provider now carries the suggested sub
                    if _exact(r.suggested_subcategory) != _exact(p.subcategory):
                        continue
                    # (b) the stale primary == primary the OLD subcategory mapped to
                    old_primary = primary_for_subcategory(r.current_subcategory)
                    if old_primary is not None and old_primary == current:
                        matched = r
                        break
            if matched is not None:
                bucket = "stale_recat"
                recat_match = how
                recat_notes = (
                    f"{matched.current_subcategory}->{matched.suggested_subcategory} "
                    f"[{matched.confidence}] {matched.notes}"
                )
            else:
                bucket = "review"

        out.append(
            MismatchRow(
                provider_id=p.id,
                provider_name=p.provider_name,
                subcategory=p.subcategory,
                current_primary=current,
                expected_primary=expected,
                bucket=bucket,
                recat_match=recat_match,
                recat_notes=recat_notes,
            )
        )
    return out


def _db_kind() -> str:
    """Non-secret description of the target DB (driver + database name, no creds)."""
    url = engine.url
    return f"{url.drivername} db={url.database!r} host={url.host!r}"


def print_report(rows: list[MismatchRow], total_classified: int) -> None:
    by_bucket: Counter = Counter(r.bucket for r in rows)
    print(f"\nTarget DB: {_db_kind()}")
    print(f"Classified (primary_category NOT NULL) providers scanned: {total_classified}")
    print(f"Mismatches (primary != primary_for_subcategory(subcategory)): {len(rows)}")
    print(
        f"  stale_recat (SAFE auto-fix)   : {by_bucket['stale_recat']}\n"
        f"  review      (human eyeball)   : {by_bucket['review']}\n"
        f"  no_target   (subcat null/unk) : {by_bucket['no_target']}"
    )

    safe = [r for r in rows if r.bucket == "stale_recat"]
    if safe:
        print("\n--- SAFE auto-fixes (stale_recat) ---")
        for r in sorted(safe, key=lambda r: r.provider_name.lower()):
            print(
                f"  [{r.provider_id}] {r.provider_name}: subcat={r.subcategory} | "
                f"primary {r.current_primary} -> {r.expected_primary}  "
                f"({r.recat_match}: {r.recat_notes})"
            )

    review = [r for r in rows if r.bucket == "review"]
    if review:
        print("\n--- REVIEW (needs a human eyeball) ---")
        trans: Counter = Counter(
            f"{r.current_primary} -> {r.expected_primary}" for r in review
        )
        print("  transition histogram (current_primary -> expected):")
        for t, n in trans.most_common():
            print(f"    {n:4d}  {t}")
        print("  rows:")
        for r in sorted(review, key=lambda r: (r.current_primary or "", r.provider_name.lower())):
            print(
                f"    [{r.provider_id}] {r.provider_name}: subcat={r.subcategory} | "
                f"primary {r.current_primary} -> {r.expected_primary}"
            )

    no_target = [r for r in rows if r.bucket == "no_target"]
    if no_target:
        print(f"\n--- NO TARGET ({len(no_target)}: subcategory NULL/unmapped, NOT auto-fixable) ---")
        sub_hist: Counter = Counter((r.subcategory or "<NULL>") for r in no_target)
        for sub, n in sub_hist.most_common():
            print(f"    {n:4d}  subcat={sub}")


def write_csv(rows: list[MismatchRow], out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "provider_id",
                "provider_name",
                "subcategory",
                "current_primary",
                "expected_primary",
                "bucket",
                "recat_match",
                "recat_notes",
            ]
        )
        for r in sorted(rows, key=lambda r: (r.bucket, r.provider_name.lower())):
            w.writerow(
                [
                    r.provider_id,
                    r.provider_name,
                    r.subcategory or "",
                    r.current_primary or "",
                    r.expected_primary or "",
                    r.bucket,
                    r.recat_match,
                    r.recat_notes,
                ]
            )
    print(f"\nWrote {len(rows)} rows -> {out_path}")


def run(*, recat_csv: Path, out_path: Path | None) -> list[MismatchRow]:
    recat_rows = load_recat_rows(recat_csv)
    db = SessionLocal()
    try:
        total_classified = (
            db.query(Provider)
            .filter(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                Provider.primary_category.isnot(None),
            )
            .count()
        )
        rows = classify(db, recat_rows)
    finally:
        db.close()
    print_report(rows, total_classified)
    if out_path is not None:
        write_csv(rows, out_path)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recat-csv", type=Path, default=DEFAULT_RECAT_CSV, help="recat CSV for stale-primary fingerprinting"
    )
    parser.add_argument("--out", type=Path, default=None, help="write full row detail to this CSV")
    args = parser.parse_args()
    run(recat_csv=args.recat_csv, out_path=args.out)


if __name__ == "__main__":
    main()
