"""Apply the Phase 5.11 pets (cat-11) data-quality audit decisions.

Mirrors outputs/apply_phase5_10_lodging_audit.py shape with 5.11-specific
slices -- simpler still: only Slice E (NEW creates) fires; Slices B/C/D
all have 0 entries per the 2 audit decisions in
outputs/phase5_11_pets_audit.md.

  - **Slice E NEW creates cat-11 (25 entries):** ALL 25 ambig-skipped
    place_ids from the 1.4 load were classified as Slice E (real pet
    businesses incorrectly flagged by the reconcile-50m-geo-noise
    pattern -- each one is a real LHC pet business sitting next to a
    non-pet entity in a strip mall). NONE of the 25 are actual
    cross-cat overlaps; the audit dump aggregates show 0 same-cat
    match (no candidate matched an existing cat-11 entity) and 25
    cross-cat matches that are all benign geo-proximity false
    positives.

    Source: outputs/phase5_11_ambig_audit_data.json (written by
    outputs/phase5_11_ambig_audit_dump.py). The 25 records are
    enumerated by place_id at runtime -- no hardcoded name list (the
    "Beautiful Beards Pet Spaw" same-name distinct-place_id pattern
    surfaced in 5.11 makes a by-name lookup ambiguous; by-place_id is
    the authoritative key).

Slices B/C/D/F/G summary (no apply actions):
  - **Slice A KEEP:** 17 cat-11 entries (post-1.4 load + sustainability
    re-run) all stay -- 5 baseline (4 vets + Exotic Pet Kingdom) + 12
    newly-inserted (5 pet_care/pet_store first-run + 7 pet_care/service
    sustainability-resolved). Wait -- spot-check showed 13 not 17;
    the 4-entry delta is because 4 of the 12 first-run inserts had
    primary='store' and went to cat-8 shopping-essentials via the
    pre-Phase-5 store direct mapping (per kickoff 2 tertiary axis:
    "Mixed retail venues stay correctly categorized in cat-8").
    Adjusted: Slice A KEEP = 13 cat-11 + 3 cat-8 pet-retail (PetSmart,
    Doggie Shades, Rok Dog Leashes; V1.5 DUAL ADD cat-11 carry).
  - **Slice B FLIP cat-X -> cat-11:** 0. (No real cross-cat overlap;
    all "matches" are strip-mall geo-noise.)
  - **Slice C FLIP cat-11 -> cat-X:** 0. (No entries need to leave
    cat-11.)
  - **Slice D DUAL ADD:** 0 for V1. (V1.5 carry: 3 cat-8 pet-retail
    entries + 3 Beautiful Beards franchise + 3 PetSmart franchise
    multi-place_id consolidations.)
  - **Slice F KEEP-ambig:** 0. (All 25 ambig records are real pet
    businesses worth creating; none are true geo-dupes.)
  - **Slice G DRAFT/DELETE:** 0. (5 candidates have 0 reviews
    [Obedience Please, PetSmart Grooming, PetSmart Dog Training,
    Penney's Pampered Pawz, TagWorks] -- defaulting to draft=0 per
    5.10 SHIP cadence; operator can DRAFT specific entries
    post-apply if needed.)

Source of truth for the decisions:
``outputs/phase5_11_pets_audit.md`` 4 (Slice E enumeration).

Strategy:
- **Slice E NEW create:** read place_ids from
  ``outputs/phase5_11_ambig_audit_data.json``; for each, look up
  enrichment row by place_id; construct Provider via
  ``places_load.row_to_provider_kwargs``; call
  ``create_provider_and_entity`` which dual-writes Entity + Location +
  EntityCategory + ContactPoint + SourceEvidence. All 25 candidates
  use default entity_type='commercial' (pet-service businesses are
  fee-based, staffed) and draft=False.

Net effect:
    /category/pets               : 13 -> 38 (25 NEW)
    All other categories         : unchanged

Re-run safety: idempotent. NEW creates dedupe on google_place_id; if a
candidate place_id is already a Provider row (from a prior run of this
script or a manual flush), the script SKIPs the create.

DB-write -- stop FastAPI dev server first to avoid events.db lock per
the 5.4 / 5.5 / 5.6 / 5.7 / 5.8 / 5.9 / 5.10 close-out gotcha.

5.9 reporting-bug fix: uses ``select(func.count())`` for the post-apply
count instead of ``.all()`` length, per the 5.9 2 in-session reporting
quirk where the autoflush behavior made the .all() count off by N.

IMPORTANT: Per the 5.8 / 5.9 / 5.10 close-out lesson, DB-verify the
"existing entity in cat-X" premise BEFORE authoring NEW creates. All
25 Slice E decisions in this script were DB-verified via
outputs/phase5_11_dupe_check.py [5] before the audit doc was finalized
-- aggregates show 0 same-category match, meaning none of the 25
candidates have an existing cat-11 entity within 75m (the geo-noise
matches are all in OTHER cats; sustainability commit at 1dd443a
shipped the (None, "pets") catch-all + pet_care direct mapping so all
25 will resolve to cat-11 cleanly).

Usage:
    python outputs/apply_phase5_11_pets_audit.py --dry-run
    python outputs/apply_phase5_11_pets_audit.py
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
AMBIG_JSON_PATH = ROOT / "outputs" / "phase5_11_ambig_audit_data.json"


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


def _load_slice_e_pids() -> list[tuple[str, str]]:
    """Read place_ids + display names from the ambig audit JSON dump.

    Returns list of (place_id, display_name) tuples in the order they
    appear in the JSON (sorted by place_id per the dump script).
    """
    if not AMBIG_JSON_PATH.exists():
        raise SystemExit(
            f"missing: {AMBIG_JSON_PATH}. "
            "Run `python outputs/phase5_11_ambig_audit_dump.py` first."
        )
    records = json.loads(AMBIG_JSON_PATH.read_text(encoding="utf-8"))
    return [
        (rec["candidate"]["place_id"], rec["candidate"].get("name") or "(noname)")
        for rec in records
    ]


def _create_new_entity_in_cat11(
    session,
    row: dict,
    cat11_id: int,
    *,
    draft: bool = False,
):
    """Construct Provider from enriched row + call create_provider_and_entity.

    Returns (provider, entity) on success; None if a Provider with the
    same google_place_id already exists (idempotent re-run skip).

    Forces category_id=cat11_id regardless of what the resolver would
    pick. All 25 Slice E candidates have pets-shape primary_types
    (pet_care / service / pet_store / store) that resolve to cat-11
    via the 5.11 1 sustainability commit (1dd443a) -- but explicit
    override here protects against future resolver drift.
    """
    pid = row["place_id"]
    existing = session.scalars(
        select(Provider).where(Provider.google_place_id == pid)
    ).first()
    if existing is not None:
        return None  # already created (idempotent skip)

    kwargs = row_to_provider_kwargs(row)
    kwargs["category_id"] = cat11_id
    kwargs["draft"] = draft

    prov = Provider(**kwargs)
    session.add(prov)
    prov, ent = create_provider_and_entity(session, prov)

    # All 25 Slice E candidates stay entity_type='commercial' (pets-
    # domain businesses are fee-based, staffed). The 5.11 1
    # sustainability commit at 1dd443a has pet_care/dog_groomer/
    # pet_boarding/dog_trainer all as commercial; pre-Phase-5
    # pet_store/veterinary_care also commercial; service primary
    # routes via the catch-all but is treated as commercial for cat-11.
    # No entity_type override needed.
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

    slice_e_pids = _load_slice_e_pids()
    print(f"[apply] loaded {len(slice_e_pids)} Slice E candidates from ambig dump")

    with SessionLocal() as session:
        slug_to_id: dict[str, int] = {
            c.slug: c.id for c in session.scalars(select(Category)).all()
        }
        cat11_id = slug_to_id.get("pets")
        if cat11_id is None:
            raise SystemExit("ERROR: pets slug not found in categories table")
        print(f"[apply] pets category_id = {cat11_id}")

        # Pre-apply cat-11 count (baseline for the delta report)
        pre_apply_count = session.scalar(
            select(func.count(EntityCategory.entity_id)).where(
                EntityCategory.category_id == cat11_id
            )
        )
        print(f"[apply] pre-apply cat-11 EntityCategory rows: {pre_apply_count}")

        # Slice E -- 25 NEW entity creates in cat-11
        print("\n=== Slice E: 25 NEW entity creates in cat-11 pets ===")
        slice_e_created = 0
        slice_e_skipped = 0
        slice_e_missing = 0
        for pid, target_name in slice_e_pids:
            row = enrichment.get(pid)
            if row is None:
                print(f"  [MISSING] enrichment row not found for {pid!r} ({target_name!r})")
                slice_e_missing += 1
                continue
            result = _create_new_entity_in_cat11(session, row, cat11_id)
            if result is None:
                print(f"  [skip] already exists: {target_name!r} ({pid})")
                slice_e_skipped += 1
            else:
                prov, ent = result
                disp_name = (ent.name or "(noname)")[:60]
                primary = row.get("primary_type") or "(none)"
                print(
                    f"  [create] {disp_name!r:62s} "
                    f"entity_type={ent.entity_type} "
                    f"primary={primary!r}"
                )
                slice_e_created += 1

        if slice_e_missing > 0:
            print(
                "  [WARNING] missing place_ids indicate enrichment cache lookup "
                "failure -- verify outputs/phase5_11_ambig_audit_data.json "
                "matches the enrichment cache by re-running "
                "outputs/phase5_11_ambig_audit_dump.py before applying."
            )

        # Force flush so the in-session COUNT below sees the new rows
        # (5.9 2 reporting-bug fix: without this, the COUNT may report
        # the pre-apply value due to autoflush quirk).
        session.flush()

        # Post-apply count using select(func.count()) (NOT .all() length)
        # -- 5.9 2 reporting-bug fix.
        post_apply_count = session.scalar(
            select(func.count(EntityCategory.entity_id)).where(
                EntityCategory.category_id == cat11_id
            )
        )

        print(
            "\n=== Summary ===\n"
            f"  Slice E NEW creates cat-11:    {slice_e_created} created, "
            f"{slice_e_skipped} skipped, {slice_e_missing} missing"
        )

        delta = post_apply_count - pre_apply_count
        print(
            f"\n  Post-apply cat-11 EntityCategory rows: {post_apply_count} "
            f"(pre-apply {pre_apply_count}; delta {delta:+}; "
            "target >= 20 per kickoff 6 gate item 1)"
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
