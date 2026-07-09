"""Approve the high-confidence, non-marine web-audit provider contributions.

Generalizes ``scripts/approve_marine_contributions.py``: instead of the hardcoded
marine combo (category='lake_recreation' / primary='on-the-water'), it derives
per subcategory:

  * ``primary_category`` = ``primary_for_subcategory(hint)``  — taxonomy, deterministic.
    (Verified against prod: this equals the dominant existing primary for every
    subcategory in this batch, so a new row routes onto /lake-havasu/{hint}
    exactly like its existing peers.)
  * legacy ``category`` = the dominant existing ``Provider.category`` for that
    subcategory among active, non-draft rows (peer-consistent — the new row
    behaves like its neighbours on every surface that reads the legacy column).
    A few subcategories whose existing rows are too thin or mis-filed to trust
    get a reviewed override (``_CATEGORY_OVERRIDES``), flagged in --dry-run.

CONFIDENCE GATE: every contribution is joined back to
``category_coverage_candidates_2026-06-15.csv`` by business name. ONLY rows whose
CSV ``confidence == "high"`` are approved. "med" / "low" / no-join are listed and
HELD (never approved here).

Scope guard: only ``status=pending`` + ``source=operator_backfill`` +
``entity_type=provider`` + ``submission_category_hint`` NOT in the marine set are
considered. Marine rows and med/low rows are never touched.

Approval uses ``approve_contribution_as_provider`` (the admin-form path); it sets
``category`` only, so we set ``subcategory``+``primary_category`` on the returned
Provider afterward.

Usage (Windows / PowerShell):
    .venv\\Scripts\\python.exe scripts\\approve_nonmarine_contributions.py --dry-run
    .venv\\Scripts\\python.exe scripts\\approve_nonmarine_contributions.py            # approve high-confidence
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func as sa_func  # noqa: E402

from app.categories.queries import route_provider_filter  # noqa: E402
from app.categories.router import _bucket_route_for_subcategory  # noqa: E402
from app.categories.subcategories import primary_for_subcategory, subcategory_by_slug  # noqa: E402
from app.contrib.approval_service import approve_contribution_as_provider  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Provider  # noqa: E402
from app.schemas.contribution import ProviderApprovalFields  # noqa: E402

MARINE_SLUGS = {"marine-repair", "marine-dealers", "marine-supply", "on-the-water"}
CSV_PATH = _ROOT / "category_coverage_candidates_2026-06-15.csv"

# Subcats whose existing prod rows are too thin / mis-filed to trust as an
# empirical legacy-category signal. Reviewed values (primary_category is still
# taxonomy-derived); each is flagged in --dry-run for explicit confirmation.
_CATEGORY_OVERRIDES: dict[str, str] = {
    "biking": "recreation",  # only 1 existing biking row, mis-filed as 'auto'
    "golf": "recreation",  # existing split recreation(2)/food_drink(2); food_drink = course eateries mis-filed
    "rv-parks": "lodging",  # 0 existing rv-parks rows; 'lodging' fits the stay bucket + lodging-vacation-rentals primary
}

_PHONE_RE = re.compile(r"^\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}$")


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def _parse_notes(notes: str | None) -> tuple[str | None, str | None, str | None]:
    """Split the loader's "address · phone · notes" blob into parts (address
    first; phone, when present, the next phone-shaped segment; rest = desc)."""
    parts = [p.strip() for p in (notes or "").split(" · ") if p.strip()]
    address: str | None = None
    phone: str | None = None
    desc_parts: list[str] = []
    for i, p in enumerate(parts):
        if phone is None and _PHONE_RE.match(p):
            phone = p
        elif address is None and i == 0:
            address = p
        else:
            desc_parts.append(p)
    return address, phone, (" · ".join(desc_parts) or None)


def _legacy_category(db, hint: str) -> tuple[str | None, str]:
    """(legacy category, provenance) for a subcategory."""
    if hint in _CATEGORY_OVERRIDES:
        return _CATEGORY_OVERRIDES[hint], "OVERRIDE (confirm)"
    rows = (
        db.query(Provider.category, sa_func.count(Provider.id))
        .filter(
            Provider.subcategory == hint,
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
        .group_by(Provider.category)
        .all()
    )
    if not rows:
        return None, "NO EXISTING ROWS"
    rows = sorted(rows, key=lambda r: -r[1])
    top_cat, top_n = rows[0]
    total = sum(n for _, n in rows)
    return top_cat, f"dominant {top_n}/{total}"


def _landing_count(db, subcat: str) -> int:
    """Active providers the /lake-havasu/{subcat} landing would list (router-exact)."""
    sub = subcategory_by_slug(subcat)
    route = _bucket_route_for_subcategory(sub.bucket_id) if sub else None
    if route is None:
        return 0
    return (
        db.query(Provider)
        .filter(
            route_provider_filter(route),
            Provider.subcategory == subcat,
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
        .count()
    )


def _confidence_by_name() -> dict[str, str]:
    out: dict[str, str] = {}
    with CSV_PATH.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[_norm(row.get("business"))] = (row.get("confidence") or "").strip().lower()
    return out


def run(*, dry_run: bool = True, confidence_tiers: frozenset[str] = frozenset({"high"})) -> Counter:
    counts: Counter = Counter()
    conf_by_name = _confidence_by_name()
    db = SessionLocal()
    try:
        rows = (
            db.query(Contribution)
            .filter(
                Contribution.status == "pending",
                Contribution.source == "operator_backfill",
                Contribution.entity_type == "provider",
            )
            .order_by(Contribution.submission_category_hint, Contribution.id)
            .all()
        )
        nonmarine = [r for r in rows if (r.submission_category_hint or "").strip() not in MARINE_SLUGS]

        # Duplicate guard: never mint a second live provider for a name that already
        # exists (active). Lower-confidence web-audit rows are likelier to collide.
        existing_names = {
            _norm(n)
            for (n,) in db.query(Provider.provider_name).filter(Provider.is_active.is_(True)).all()
        }

        selected: list[Contribution] = []
        held: list[tuple[Contribution, str]] = []
        dup: list[Contribution] = []
        for c in nonmarine:
            conf = conf_by_name.get(_norm(c.submission_name)) or "NO-JOIN"
            if conf not in confidence_tiers:
                held.append((c, conf))
            elif _norm(c.submission_name) in existing_names:
                dup.append(c)
            else:
                selected.append(c)

        # ---- HELD (tier not selected): listed, never approved ----
        print(f"HELD (tier not in {sorted(confidence_tiers)}) - {len(held)} rows:")
        for c, conf in sorted(held, key=lambda t: (t[0].submission_category_hint or "", t[0].id)):
            print(f"  [{conf}] #{c.id} [{c.submission_category_hint}] {c.submission_name}")

        # ---- DUP-SKIP: a same-name active provider already exists ----
        if dup:
            print(f"\nDUP-SKIP (same-name active provider exists) - {len(dup)} rows:")
            for c in sorted(dup, key=lambda x: x.id):
                print(f"  #{c.id} [{c.submission_category_hint}] {c.submission_name}")
            counts["dup_skip"] = len(dup)

        # ---- SELECTED: group by subcategory, derive category/primary ----
        by_sub: dict[str, list[Contribution]] = defaultdict(list)
        for c in selected:
            by_sub[(c.submission_category_hint or "").strip()].append(c)

        print(
            f"\n{'WOULD APPROVE' if dry_run else 'APPROVING'} {len(selected)} rows "
            f"(tiers={sorted(confidence_tiers)}):"
        )
        affected: list[str] = []
        for hint in sorted(by_sub):
            primary = primary_for_subcategory(hint)
            category, prov = _legacy_category(db, hint)
            flag = "  <-- CONFIRM" if prov.startswith("OVERRIDE") else ""
            before = _landing_count(db, hint)
            print(
                f"\n  == {hint}  cat={category!r} ({prov}) primary={primary!r}  "
                f"[listed now: {before}]{flag}"
            )
            if category is None:
                print("     SKIPPING subcategory — no legacy category could be derived (ask).")
                counts["skip_no_category"] += len(by_sub[hint])
                continue
            affected.append(hint)
            for c in by_sub[hint]:
                address, phone, desc = _parse_notes(c.submission_notes)
                website = (c.submission_url or "").strip() or None
                print(
                    f"     {'WOULD APPROVE' if dry_run else 'APPROVED'} #{c.id} {c.submission_name}\n"
                    f"         addr={address!r} phone={phone!r} site={website!r}"
                )
                counts["approve"] += 1
                if not dry_run:
                    pf = ProviderApprovalFields(
                        name=c.submission_name,
                        address=address,
                        phone=phone,
                        hours=None,
                        description=desc,
                        website=website,
                    )
                    new_prov = approve_contribution_as_provider(db, c.id, pf, category)
                    new_prov.subcategory = hint
                    new_prov.primary_category = primary
                    db.add(new_prov)
                    db.commit()

        if not dry_run and affected:
            print("\nLanding counts (after):")
            for hint in sorted(set(affected)):
                print(f"  {hint}: {_landing_count(db, hint)}")
    finally:
        db.close()

    verb = "would approve" if dry_run else "approved"
    print(f"\n{verb} {counts['approve']} contributions (tiers={sorted(confidence_tiers)})")
    if counts["dup_skip"]:
        print(f"  dup-skipped (same-name active provider): {counts['dup_skip']}")
    if counts["skip_no_category"]:
        print(f"  skipped (no derivable category): {counts['skip_no_category']}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="preview without writing")
    parser.add_argument(
        "--confidence",
        default="high",
        help="comma-separated CSV confidence tiers to approve (default: high)",
    )
    args = parser.parse_args()
    tiers = frozenset(s.strip().lower() for s in args.confidence.split(",") if s.strip())
    run(dry_run=args.dry_run, confidence_tiers=tiers or frozenset({"high"}))


if __name__ == "__main__":
    main()
