"""T2.1 — catalog-wide dedupe PROPOSAL report (dry-run only).

Runs the S1 clustering engine (:mod:`app.dedupe.cluster`) over every active
Provider and writes a proposed-resolution report: one CSV row per provider in a
multi-row cluster, tagged with its cluster, the engine's relationship guess
(duplicate / multi_location / parent_child), and the proposed action.

**This script never writes to the catalog.** Per the remediation plan the apply
step is gated behind Casey's review of THIS report — retiring clones, setting
``location_group_id`` / ``parent_provider_id`` and recording ``DedupeResolution``
rows lands in a follow-up once the cluster list is approved. ``--apply`` is
intentionally disabled so nobody runs a half-built writer by accident.

    .venv\\Scripts\\python.exe scripts\\dedupe_catalog.py            # write the report
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.dedupe.cluster import ProviderRecord, cluster_providers  # noqa: E402

_REPORT_CSV = "docs/audits/2026-07/dedupe_catalog_proposal_2026-07-06.csv"

# What an approved apply would do to each member, per relationship type.
_ACTION = {
    ("duplicate", True): "keep (primary)",
    ("duplicate", False): "retire -> merged_into primary (is_active=False)",
    ("multi_location", True): "keep (primary) + share location_group_id",
    ("multi_location", False): "keep (sibling) + share location_group_id",
    ("parent_child", True): "keep (parent)",
    ("parent_child", False): "keep (child) + set parent_provider_id",
}


def _load_records(db) -> list[ProviderRecord]:
    rows = db.execute(
        select(
            Provider.id,
            Provider.provider_name,
            Provider.address,
            Provider.phone,
            Provider.google_place_id,
            Provider.google_review_count,
            Provider.verified,
            Provider.slug,
        ).where(Provider.is_active.is_(True))
    ).all()
    return [
        ProviderRecord(
            id=str(r.id),
            name=r.provider_name or "",
            address=r.address,
            phone=r.phone,
            google_place_id=r.google_place_id,
            review_count=int(r.google_review_count or 0),
            verified=bool(r.verified),
            slug=r.slug,
        )
        for r in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Catalog-wide dedupe proposal report.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="DISABLED — apply lands in a follow-up after Casey reviews the report",
    )
    args = parser.parse_args(argv)
    if args.apply:
        print(
            "--apply is intentionally disabled. This script only PROPOSES clusters; "
            "review the report with Casey, then the gated apply script performs the "
            "approved retires / location_group_id / parent_provider_id writes."
        )
        return 2

    with SessionLocal() as db:
        records = _load_records(db)
    clusters = cluster_providers(records)

    rel_counts: Counter[str] = Counter()
    affected_rows = 0
    retire_count = 0
    out_path = Path(_REPORT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "cluster_id", "relationship_type", "reason", "role", "proposed_action",
            "provider_id", "provider_name", "address", "phone", "google_place_id",
            "review_count", "verified", "slug",
        ])
        for idx, c in enumerate(clusters, start=1):
            rel_counts[c.relationship_type] += 1
            for m in c.members:
                is_primary = m.id == c.primary.id
                role = "primary" if is_primary else (
                    "clone" if c.relationship_type == "duplicate"
                    else "sibling" if c.relationship_type == "multi_location"
                    else "child"
                )
                action = _ACTION[(c.relationship_type, is_primary)]
                if c.relationship_type == "duplicate" and not is_primary:
                    retire_count += 1
                affected_rows += 1
                w.writerow([
                    idx, c.relationship_type, c.reason, role, action,
                    m.id, m.name, m.address or "", m.phone or "", m.google_place_id or "",
                    m.review_count, m.verified, m.slug or "",
                ])

    print(f"active providers scanned : {len(records)}")
    print(f"clusters (size >= 2)     : {len(clusters)}")
    print(f"providers in a cluster   : {affected_rows}")
    print(f"  duplicate clusters     : {rel_counts['duplicate']}")
    print(f"  multi_location clusters: {rel_counts['multi_location']}")
    print(f"  parent_child clusters  : {rel_counts['parent_child']}")
    print(f"clones proposed to retire: {retire_count}")
    print(f"\nreport written: {out_path}")
    print("DRY RUN — no catalog writes. Review the report before any apply (prod-data gate).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
