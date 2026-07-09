"""Approve the marine batch of pending web-audit provider contributions.

Strictly scoped: ONLY contributions with status='pending', source='operator_backfill',
entity_type='provider', and submission_category_hint in the four marine slugs are
considered. Anything outside that set is ignored (never touched).

Each row is approved via ``approve_contribution_as_provider`` — the exact path the
admin "Approve" form uses — which mints a live Provider + Entity and flips the
contribution to 'approved'. That function sets ``Provider.category`` only, so
afterward we set ``subcategory`` (= the category hint) and ``primary_category``
(= the canonical primary for that subcategory) so the new shop surfaces on its
``/lake-havasu/{subcategory}`` landing (which filters ``Provider.subcategory == slug``).

The legacy ``category`` we pass is ``lake_recreation`` — the value 8/8 of the existing
active marine-repair rows (and the dominant share of dealers/supply/on-the-water) carry
in prod, so the new rows match their proven routing combo exactly rather than guessing.

ProviderApprovalFields are built from the contribution: name=submission_name,
website=submission_url, and address/phone parsed back out of submission_notes (the
loader joined "address · phone · notes" with " · "; address is always first, phone —
when present — second). The parsed values are shown in --dry-run so they can be
eyeballed before any write.

Usage (Windows / PowerShell):
    .venv\\Scripts\\python.exe scripts\\approve_marine_contributions.py --dry-run
    .venv\\Scripts\\python.exe scripts\\approve_marine_contributions.py            # approve
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.queries import route_provider_filter  # noqa: E402
from app.categories.router import _bucket_route_for_subcategory  # noqa: E402
from app.categories.subcategories import primary_for_subcategory, subcategory_by_slug  # noqa: E402
from app.contrib.approval_service import approve_contribution_as_provider  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Provider  # noqa: E402
from app.schemas.contribution import ProviderApprovalFields  # noqa: E402

MARINE_SLUGS = ("marine-repair", "marine-dealers", "marine-supply", "on-the-water")
# Legacy Provider.category to stamp — matches the dominant existing marine combo in prod.
LEGACY_CATEGORY = "lake_recreation"

# Per-name description overrides. Gibbs' source CSV row had an unescaped comma in
# its Yelp URL, so the CSV parser split it at ingest and the real note ("Propeller
# sales/repair") was displaced by a stray "+AZ". Restore the true note so the live
# listing reads cleanly (Casey-approved 2026-06-16).
_DESC_OVERRIDES: dict[str, str] = {
    "Gibbs Propeller Service": "Propeller sales/repair",
}

_PHONE_RE = re.compile(r"^\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}$")


def _parse_notes(notes: str | None) -> tuple[str | None, str | None, str | None]:
    """Split the loader's "address · phone · notes" blob back into parts.

    Address is always first; phone (when present) is the next phone-shaped
    segment; everything else is the description. Returns (address, phone, desc).
    """
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


def _landing_count(db, subcat: str) -> int:
    """Active providers the /lake-havasu/{subcat} landing would list.

    Mirrors the router exactly: it derives the bucket route the same way
    ``render_subcategory_landing`` does, then applies that route's filter plus
    the subcategory facet.
    """
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


def run(*, dry_run: bool = True) -> Counter:
    counts: Counter = Counter()
    db = SessionLocal()
    try:
        rows = (
            db.query(Contribution)
            .filter(
                Contribution.status == "pending",
                Contribution.source == "operator_backfill",
                Contribution.entity_type == "provider",
                Contribution.submission_category_hint.in_(MARINE_SLUGS),
            )
            .order_by(Contribution.submission_category_hint, Contribution.id)
            .all()
        )

        # Duplicate guard: never mint a second live provider for a name that already
        # exists (active). Without this the batch silently created dups (2026-06-16).
        existing_names = {
            " ".join((n or "").split()).strip().lower()
            for (n,) in db.query(Provider.provider_name).filter(Provider.is_active.is_(True)).all()
        }

        print("Existing active landing counts (before):")
        for s in MARINE_SLUGS:
            print(f"  {s}: {_landing_count(db, s)}")
        print(f"\n{len(rows)} pending marine contributions to approve:\n")

        for c in rows:
            hint = (c.submission_category_hint or "").strip()
            if hint not in MARINE_SLUGS:  # belt-and-suspenders; query already scopes this
                counts["skip_out_of_scope"] += 1
                print(f"  SKIP (out of marine scope): #{c.id} {c.submission_name} [{hint}]")
                continue
            if " ".join((c.submission_name or "").split()).strip().lower() in existing_names:
                counts["dup_skip"] += 1
                print(f"  DUP-SKIP (same-name active provider exists): #{c.id} {c.submission_name}")
                continue
            address, phone, desc = _parse_notes(c.submission_notes)
            desc = _DESC_OVERRIDES.get((c.submission_name or "").strip(), desc)
            website = (c.submission_url or "").strip() or None
            primary = primary_for_subcategory(hint)
            print(
                f"  {'WOULD APPROVE' if dry_run else 'APPROVED'} #{c.id} "
                f"[{hint} | cat={LEGACY_CATEGORY} | primary={primary}]: {c.submission_name}\n"
                f"      addr={address!r} phone={phone!r} site={website!r}\n"
                f"      desc={(desc or '')[:90]!r}"
            )
            counts[hint] += 1
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
                prov = approve_contribution_as_provider(db, c.id, pf, LEGACY_CATEGORY)
                # approval_service sets category only; pin the leaf + canonical primary
                # so the row routes onto /lake-havasu/{hint}.
                prov.subcategory = hint
                prov.primary_category = primary
                db.add(prov)
                db.commit()

        if not dry_run:
            print("\nExisting active landing counts (after):")
            for s in MARINE_SLUGS:
                print(f"  {s}: {_landing_count(db, s)}")
    finally:
        db.close()

    verb = "would approve" if dry_run else "approved"
    by_sub = ", ".join(f"{s} {counts[s]}" for s in MARINE_SLUGS if counts[s])
    print(f"\n{verb} {counts['approve']} marine contributions ({by_sub})")
    if counts["dup_skip"]:
        print(f"  dup-skipped (same-name active provider): {counts['dup_skip']}")
    if counts["skip_out_of_scope"]:
        print(f"  skipped out-of-scope: {counts['skip_out_of_scope']}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="preview without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
