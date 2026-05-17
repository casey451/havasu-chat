"""Apply the Phase 5.10 lodging-vacation-rentals data-quality audit decisions.

Mirrors outputs/apply_phase5_9_classes_audit.py shape with 5.10-specific
slices -- but simpler: only Slice E (NEW creates) fires. Slices B/C/D/G
all have 0 entries per the 2 audit decisions in
outputs/phase5_10_lodging_audit.md.

  - **Slice E NEW creates cat-10 (6 entries):** 5 hotels + 1 lodging-
    primary vacation rental that were ambig-skipped in the 1 load
    because of geo-proximity to existing entities (mostly eat-drink
    venues on McCulloch Blvd N -- the strip-mall geo-noise pattern
    shared with 5.6). All 6 are confirmed NOT in DB by name + place_id
    via outputs/phase5_10_dupe_check.py [1].
      1. Heat Hotel (primary=hotel, 406r) -- with HEAT Bar
         dual-place_id observation (separate cat-1 entity at 8.6m;
         V1.5 carry).
      2. Travelodge by Wyndham Lake Havasu (primary=hotel, 901r)
      3. Knights Inn Lake Havasu City (primary=hotel, 266r)
      4. LAKE PLACE INN (primary=motel, 64r)
      5. Holiday Inn Express & Suites Lake Havasu - London Bridge by
         IHG (primary=hotel, 619r)
      6. Queens Bay Resort Condominiums (primary=lodging, 69r)

Slices B/C/D/F/G summary (no apply actions):
  - **Slice A KEEP:** 67 cat-10 entries (post-1.6+1.7c) all stay; HEAT
    Bar stays in cat-1.
  - **Slice B FLIP cat-X -> cat-10:** 0. (HEAT Bar considered but is
    named "HEAT Bar" -- its identity is a bar, not the hotel; the
    primary='hotel' tag is a Google Maps data quirk.)
  - **Slice C FLIP cat-10 -> cat-X:** 0. (no entries need to leave
    cat-10.)
  - **Slice D DUAL ADD cat-3 to cat-10:** 0. (waterfront-resort
    DB-verify in dupe-check [3] confirmed Lakeside Inn + Havasu Dunes
    Resort + GetAways at Havasu Dunes Resort are all INLAND coordinates;
    no waterfront-primary candidates among existing or new cat-10.)
  - **Slice F KEEP-ambig:** 31 records (29 lake_recreation-domain
    geo-noise + Havasu Suites + Xanadu). All correctly remain in their
    current cats or in V1.5 carry.
  - **Slice G DRAFT/DELETE:** 0.

Source of truth for the decisions:
``outputs/phase5_10_lodging_audit.md`` 4 (Slice E enumeration).

Strategy:
- **Slice E NEW create:** look up each candidate by display_name in the
  enrichment cache; construct Provider via
  ``places_load.row_to_provider_kwargs``; call
  ``create_provider_and_entity`` which dual-writes Entity + Location +
  EntityCategory + ContactPoint + SourceEvidence. All 6 candidates use
  default entity_type='commercial' (per the 5.10 1 sustainability
  commit bf24e16 -- hotel/motel/resort_hotel/extended_stay_hotel/
  bed_and_breakfast all start commercial; lodging primary stays
  commercial per the pre-Phase-5 default).

Net effect:
    /category/lodging-vacation-rentals  : 67 -> 73 (6 NEW)
    /category/eat-drink                  : unchanged (HEAT Bar stays)
    All other categories                 : unchanged

Re-run safety: idempotent. NEW creates dedupe on google_place_id; if a
candidate place_id is already a Provider row (from a prior run of this
script or a manual flush), the script SKIPs the create.

DB-write -- stop FastAPI dev server first to avoid events.db lock per
the 5.4 / 5.5 / 5.6 / 5.7 / 5.8 / 5.9 close-out gotcha.

5.9 reporting-bug fix: uses ``select(func.count())`` for the post-apply
count instead of ``.all()`` length, per the 5.9 2 in-session reporting
quirk where the autoflush behavior made the .all() count off by N.

IMPORTANT: Per the 5.8 / 5.9 close-out lesson, DB-verify the "existing
entity in cat-X" premise BEFORE authoring NEW creates. All 6 Slice E
decisions in this script were DB-verified via
outputs/phase5_10_dupe_check.py [1] before the audit doc was finalized
-- all 6 confirmed NOT in DB by name.

Usage:
    python outputs/apply_phase5_10_lodging_audit.py --dry-run
    python outputs/apply_phase5_10_lodging_audit.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import create_provider_and_entity  # noqa: E402
from app.db.models import Category, EntityCategory, Provider  # noqa: E402
from scripts.places_load import row_to_provider_kwargs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENRICHMENT_PATH = (
    ROOT / "scripts" / "output" / "places_pull" / "enrichment_enriched.jsonl"
)

# Slice E -- NEW entity creates in cat-10 (6 entries).
# Names taken verbatim from outputs/phase5_10_ambig_audit_data.json +
# outputs/phase5_10_dupe_check_stdout.txt [5] (full 37-record ambig
# enumeration). Each name resolves to a place_id via the enrichment
# cache at runtime (`_pid_for_name`).
SLICE_E_NEW_CREATES_BY_NAME: list[str] = [
    "Heat Hotel",                                                       # hotel, 406r
    "Travelodge by Wyndham Lake Havasu",                                # hotel, 901r
    "Knights Inn Lake Havasu City",                                     # hotel, 266r
    "LAKE PLACE INN",                                                   # motel, 64r
    "Holiday Inn Express & Suites Lake Havasu - London Bridge by IHG",  # hotel, 619r
    "Queens Bay Resort Condominiums",                                   # lodging, 69r
]


def _load_enrichment_by_pid() -> dict[str, dict]:
    """Load enrichment_enriched.jsonl indexed by place_id."""
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    out: dict[str, dict] = {}
    for line in ENRICHMENT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pid = row.get("place_id")
        if pid:
            out[pid] = row
    return out


def _pid_for_name(enrichment: dict[str, dict], target_name: str) -> str | None:
    """Find a place_id whose display_name matches target_name."""
    for pid, row in enrichment.items():
        if row.get("display_name") == target_name:
            return pid
    return None


def _create_new_entity_in_cat10(
    session,
    row: dict,
    cat10_id: int,
    *,
    draft: bool = False,
) -> tuple[Provider, object] | None:
    """Construct Provider from enriched row + call create_provider_and_entity.

    Returns (provider, entity) on success; None if a Provider with the
    same google_place_id already exists (idempotent re-run skip).

    Forces category_id=cat10_id regardless of what the resolver would
    pick. All 6 Slice E candidates have lodging-shape primary_types
    (hotel/motel/lodging) that resolve to cat-10 via the 5.10 1.7
    sustainability commit -- but explicit override here protects
    against future resolver drift.
    """
    pid = row["place_id"]
    existing = session.scalars(
        select(Provider).where(Provider.google_place_id == pid)
    ).first()
    if existing is not None:
        return None  # already created (idempotent skip)

    kwargs = row_to_provider_kwargs(row)
    kwargs["category_id"] = cat10_id
    kwargs["draft"] = draft

    prov = Provider(**kwargs)
    session.add(prov)
    prov, ent = create_provider_and_entity(session, prov)

    # All 6 Slice E candidates stay entity_type='commercial' (the
    # 5.10 1.7 sustainability commit at bf24e16 has all 5 lodging
    # primary types as commercial; the pre-Phase-5 lodging direct
    # mapping is also commercial). No entity_type override needed.
    return prov, ent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    enrichment = _load_enrichment_by_pid()
    print(f"[apply] loaded {len(enrichment)} enriched rows")

    with SessionLocal() as session:
        slug_to_id: dict[str, int] = {
            c.slug: c.id for c in session.scalars(select(Category)).all()
        }
        if "lodging-vacation-rentals" not in slug_to_id:
            raise RuntimeError("missing category slug: lodging-vacation-rentals")
        cat10_id = slug_to_id["lodging-vacation-rentals"]

        # Pre-apply cat-10 count (baseline for the delta report)
        pre_apply_count = session.scalar(
            select(func.count(EntityCategory.entity_id)).where(
                EntityCategory.category_id == cat10_id
            )
        )
        print(f"[apply] pre-apply cat-10 EntityCategory rows: {pre_apply_count}")

        # Slice E -- 6 NEW entity creates in cat-10
        print("\n=== Slice E: 6 NEW entity creates in cat-10 lodging-vacation-rentals ===")
        slice_e_created = 0
        slice_e_skipped = 0
        slice_e_missing = 0
        for target_name in SLICE_E_NEW_CREATES_BY_NAME:
            pid = _pid_for_name(enrichment, target_name)
            if pid is None:
                print(
                    f"  [MISSING] enrichment row not found by name: {target_name!r}"
                )
                slice_e_missing += 1
                continue
            row = enrichment[pid]
            result = _create_new_entity_in_cat10(session, row, cat10_id)
            if result is None:
                print(f"  [skip] already exists: {target_name!r}")
                slice_e_skipped += 1
            else:
                prov, ent = result
                print(
                    f"  [create] {ent.name!r:65s} "
                    f"entity_type={ent.entity_type} "
                    f"primary={row.get('primary_type')!r}"
                )
                slice_e_created += 1
        if slice_e_missing > 0:
            print(
                "  [WARNING] missing names indicate enrichment cache lookup "
                "failure -- verify name spellings against the dump records "
                "in outputs/phase5_10_ambig_audit_data.json before applying."
            )

        # Force flush so the in-session COUNT below sees the new rows
        # (5.9 2 reporting-bug fix: without this, the COUNT may report
        # the pre-apply value due to autoflush quirk).
        session.flush()

        # Post-apply count using select(func.count()) (NOT .all() length)
        # -- 5.9 2 reporting-bug fix.
        post_apply_count = session.scalar(
            select(func.count(EntityCategory.entity_id)).where(
                EntityCategory.category_id == cat10_id
            )
        )

        print(
            "\n=== Summary ===\n"
            f"  Slice E NEW creates cat-10:    {slice_e_created} created, "
            f"{slice_e_skipped} skipped, {slice_e_missing} missing"
        )

        delta = post_apply_count - pre_apply_count
        print(
            f"\n  Post-apply cat-10 EntityCategory rows: {post_apply_count} "
            f"(pre-apply {pre_apply_count}; delta {delta:+}; "
            "target >= 20 per kickoff 6)"
        )

        if args.dry_run:
            print("\n[dry-run] rolling back; no DB writes.")
            session.rollback()
        else:
            session.commit()
            print("\n[apply] committed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
