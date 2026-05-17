"""Apply the Phase 5.9 classes-sports-recreation data-quality audit decisions.

Mirrors outputs/apply_phase5_8_events_audit.py shape with 5.9-specific
slices:

  - **Slice B FLIP cat-5 -> cat-12 (1):** Stormy Wade Courts (tennis_court
    primary). The 5.4 HWC absorption caught it via
    ``(tennis_court, fitness_sports) -> health-wellness-care`` fallback.
    The 5.9 sustainability commit at 0af5f73 added direct mapping
    ``("tennis_court", ("classes-sports-recreation", "place"))`` which
    beats the fallback per resolver order — but existing entries need
    explicit FLIP.
  - **Slice C FLIP cat-12 -> cat-13 (2):** Knights of Columbus (civic
    org, primary=association_or_organization) + Hilltop Community Church
    (primary=church, the church itself; Hilltop Learning Center as a
    separate place_id entity stays in cat-12). Both routed to cat-12 via
    the new (None, childcare_education) catch-all from 0af5f73 but
    belong in cat-13 per primary identity.
  - **Slice D DUAL ADD cat-13 (1):** Our Lady of the Lake Catholic School
    (primary=church, name contains "Catholic School"). IS a school
    (cat-12 — preserve) AND a church (cat-13 — add).
  - **Slice E NEW creates cat-12 (3):** Lake Havasu City Aquatic Center
    (595r, swimming_pool primary, place-typed; the 5.8 §9 V1.5 carry —
    cached from 5.4 spas label, ambig-skipped by 5.9 §1 load) + Psalms
    Learning Center (school primary, commercial; in §1 ambig pool;
    co-located with Ark Center at 2700 Jamaica Blvd S) + Mohave Traffic
    School (educational_institution primary, commercial; in §1 ambig
    pool; routes to cat-12 via the new childcare_education catch-all).

Source of truth for the decisions:
``outputs/phase5_9_classes_audit.md`` §4 (Slices B/C/D/E).

Strategy:
- **Slice B/C FLIP:** look up existing entity by name, DELETE old
  EntityCategory, INSERT new EntityCategory(new_cat, is_primary=True),
  update Provider.category_id.
- **Slice D DUAL ADD:** look up existing entity by name, INSERT second
  EntityCategory(cat-13, is_primary=False) without touching cat-12 row.
  Provider.category_id stays as cat-12 (primary).
- **Slice E NEW create:** construct Provider via
  ``places_load.row_to_provider_kwargs`` from the enrichment cache;
  call ``create_provider_and_entity`` which dual-writes Entity +
  Location + EntityCategory + ContactPoint + SourceEvidence. Override
  ``Entity.entity_type='place'`` post-create for swimming_pool primary
  (per the 5.9 §1 sustainability commit commercial-vs-place split).

Usage:
    python outputs/apply_phase5_9_classes_audit.py --dry-run
    python outputs/apply_phase5_9_classes_audit.py

Net effect:
    /category/classes-sports-recreation  : 27 -> 29 (3 NEW + 1 FLIP-in
                                                     - 2 FLIPs-out)
    /category/health-wellness-care       : -1 (Stormy Wade Courts moves
                                               out via Slice B)
    /category/public-civic-resources     : +2 (Knights of Columbus +
                                               Hilltop Community Church
                                               move in via Slice C); +1
                                               more from Slice D ADD
                                               (Our Lady cross-link)

Re-run safety: idempotent. NEW creates dedupe on google_place_id; if a
candidate place_id is already a Provider row (from a prior run of this
script or a manual flush), the script SKIPs the create. FLIPs DELETE +
INSERT same row (net updated_at). DUAL ADD checks for existing
(entity_id, cat-13) before insert.

DB-write — stop FastAPI dev server first to avoid events.db lock per
the 5.4 / 5.5 / 5.6 / 5.7 / 5.8 close-out gotcha.

IMPORTANT: Per the 5.8 close-out §4 lesson, DB-verify the "existing
entity in cat-X" premise BEFORE authoring cross-cat moves. All Slice
B/C/D decisions in this script were DB-verified via
outputs/phase5_9_dupe_check.py before the audit doc was finalized.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import create_provider_and_entity  # noqa: E402
from app.db.entity_types import ENTITY_TYPE_PLACE  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402
from scripts.places_load import row_to_provider_kwargs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENRICHMENT_PATH = (
    ROOT / "scripts" / "output" / "places_pull" / "enrichment_enriched.jsonl"
)

# Slice B — FLIP cat-5 HWC -> cat-12 classes-sports-recreation (1 entry).
# Stormy Wade Courts: primary=tennis_court. The 5.9 sustainability layer
# adds tennis_court -> cat-12 (place) direct mapping; this FLIP updates
# the existing 5.4-loaded row to match.
SLICE_B_FLIP_HWC_TO_CAT12_BY_NAME: list[str] = [
    "Stormy Wade Courts",
]

# Slice C — FLIP cat-12 classes-sports-recreation -> cat-13
# public-civic-resources (2 entries). Both currently in cat-12 via the
# new (None, childcare_education) catch-all but belong in cat-13 per
# primary identity.
SLICE_C_FLIP_CAT12_TO_CAT13_BY_NAME: list[str] = [
    "Knights of Columbus",
    "Hilltop Community Church",
]

# Slice D — DUAL ADD cat-13 to existing cat-12 entries (1 entry).
# Our Lady of the Lake Catholic School: IS a school (preserve cat-12)
# AND a church (add cat-13).
SLICE_D_DUAL_ADD_CAT13_BY_NAME: list[str] = [
    "Our Lady of the Lake Catholic School",
]

# Slice E — NEW entity creates in cat-12 (3 entries).
# Listed by candidate name; the script resolves each name to a place_id
# via the enrichment cache at runtime (``_pid_for_name``). Names taken
# verbatim from outputs/phase5_9_ambig_audit_data.json + the dump
# stdout's edge-case rubric / cross-cache informational section.
SLICE_E_NEW_CREATES_BY_NAME: list[str] = [
    "Lake Havasu City Aquatic Center",  # swimming_pool, 595r — place
    "Psalms Learning Center",           # school, 0r — commercial
    "Mohave Traffic School",            # educational_institution, 0r — commercial
]

# Primary types that should be entity_type='place' (per the 5.9 §1
# sustainability commit at 0af5f73 — swimming_pool / tennis_court /
# pickleball_court all map to place).
PLACE_TYPED_PRIMARIES: frozenset[str] = frozenset({
    "swimming_pool",
    "tennis_court",
    "pickleball_court",
})


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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


def _resolve_entity_by_name(session, name: str) -> Entity | None:
    """Resolve Entity.name exact-match. Asserts at most one active row."""
    rows = session.scalars(
        select(Entity).where(Entity.name == name, Entity.is_active == 1)
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError(
            f"name-resolution collision: {len(rows)} active entities "
            f"match Entity.name={name!r}; expected exactly 1."
        )
    return rows[0]


def _create_new_entity_in_cat12(
    session,
    row: dict,
    cat12_id: int,
    *,
    draft: bool = False,
) -> tuple[Provider, Entity] | None:
    """Construct Provider from enriched row + call create_provider_and_entity.

    Returns (provider, entity) on success; None if a Provider with the
    same google_place_id already exists (idempotent re-run skip).

    Forces category_id=cat12_id regardless of what the resolver would
    pick (handles Slice E NEW creates for entries the §1 load excluded
    via --category filter; e.g., Aquatic Center cached under
    beauty_personal_care label but unambiguously cat-12 via
    swimming_pool primary).
    """
    pid = row["place_id"]
    existing = session.scalars(
        select(Provider).where(Provider.google_place_id == pid)
    ).first()
    if existing is not None:
        return None  # already created (idempotent skip)

    kwargs = row_to_provider_kwargs(row)
    kwargs["category_id"] = cat12_id
    kwargs["draft"] = draft

    prov = Provider(**kwargs)
    session.add(prov)
    prov, ent = create_provider_and_entity(session, prov)

    # Override entity_type for swimming_pool / tennis_court /
    # pickleball_court primaries per the 5.9 sustainability commit
    # (0af5f73) commercial-vs-place split.
    primary = (row.get("primary_type") or "").lower()
    if primary in PLACE_TYPED_PRIMARIES:
        ent.entity_type = ENTITY_TYPE_PLACE
    return prov, ent


def _flip_entity_to_cat(
    session, entity_id: str, new_cat_id: int
) -> None:
    """Replace all EntityCategory rows with a single (entity_id,
    new_cat_id, is_primary=True). Update Provider.category_id."""
    session.execute(
        delete(EntityCategory).where(EntityCategory.entity_id == entity_id)
    )
    session.add(
        EntityCategory(
            entity_id=entity_id,
            category_id=new_cat_id,
            is_primary=True,
            created_at=_utc_now_naive(),
        )
    )
    prov = session.scalars(
        select(Provider).where(Provider.entity_id == entity_id)
    ).first()
    if prov is not None:
        prov.category_id = new_cat_id
        prov.updated_at = _utc_now_naive()


def _dual_add_category(
    session, entity_id: str, add_cat_id: int
) -> bool:
    """Idempotent ADD of a non-primary EntityCategory row. Returns True
    if a new row was inserted; False if already present."""
    existing = session.scalars(
        select(EntityCategory).where(
            EntityCategory.entity_id == entity_id,
            EntityCategory.category_id == add_cat_id,
        )
    ).first()
    if existing is not None:
        return False
    session.add(
        EntityCategory(
            entity_id=entity_id,
            category_id=add_cat_id,
            is_primary=False,
            created_at=_utc_now_naive(),
        )
    )
    return True


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
        for needed in (
            "classes-sports-recreation",
            "health-wellness-care",
            "public-civic-resources",
        ):
            if needed not in slug_to_id:
                raise RuntimeError(f"missing category slug: {needed}")
        cat12_id = slug_to_id["classes-sports-recreation"]
        cat5_id = slug_to_id["health-wellness-care"]
        cat13_id = slug_to_id["public-civic-resources"]
        _ = cat5_id  # cat5_id not directly used (Slice B uses delete-all then insert) but documented

        # Slice B — FLIP cat-5 HWC -> cat-12 (1 entry)
        print("\n=== Slice B: FLIP cat-5 HWC -> cat-12 classes-sports-recreation ===")
        slice_b_flipped = 0
        slice_b_skipped = 0
        for name in SLICE_B_FLIP_HWC_TO_CAT12_BY_NAME:
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(f"  [skip] not found: {name!r}")
                slice_b_skipped += 1
                continue
            _flip_entity_to_cat(session, ent.id, cat12_id)
            print(f"  [flip] {name!r} -> classes-sports-recreation")
            slice_b_flipped += 1

        # Slice C — FLIP cat-12 -> cat-13 (2 entries)
        print("\n=== Slice C: FLIP cat-12 classes-sports-recreation -> cat-13 public-civic-resources ===")
        slice_c_flipped = 0
        slice_c_skipped = 0
        for name in SLICE_C_FLIP_CAT12_TO_CAT13_BY_NAME:
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(f"  [skip] not found: {name!r}")
                slice_c_skipped += 1
                continue
            _flip_entity_to_cat(session, ent.id, cat13_id)
            print(f"  [flip] {name!r} -> public-civic-resources")
            slice_c_flipped += 1

        # Slice D — DUAL ADD cat-13 (1 entry; preserve cat-12)
        print("\n=== Slice D: DUAL ADD cat-13 public-civic-resources (preserve cat-12) ===")
        slice_d_added = 0
        slice_d_skipped = 0
        for name in SLICE_D_DUAL_ADD_CAT13_BY_NAME:
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(f"  [skip] not found: {name!r}")
                slice_d_skipped += 1
                continue
            added = _dual_add_category(session, ent.id, cat13_id)
            print(
                f"  [{'add' if added else 'skip-already-exists'}] {name!r} "
                "+ public-civic-resources (cat-12 preserved as primary)"
            )
            if added:
                slice_d_added += 1
            else:
                slice_d_skipped += 1

        # Slice E — 3 NEW entity creates in cat-12
        print("\n=== Slice E: 3 NEW entity creates in cat-12 classes-sports-recreation ===")
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
            result = _create_new_entity_in_cat12(session, row, cat12_id)
            if result is None:
                print(f"  [skip] already exists: {target_name!r}")
                slice_e_skipped += 1
            else:
                prov, ent = result
                print(
                    f"  [create] {ent.name!r:55s} "
                    f"entity_type={ent.entity_type} "
                    f"primary={row.get('primary_type')!r}"
                )
                slice_e_created += 1
        if slice_e_missing > 0:
            print(
                "  [WARNING] missing names indicate enrichment cache lookup "
                "failure — verify name spellings against the dump records "
                "in outputs/phase5_9_ambig_audit_data.json before applying."
            )

        print(
            "\n=== Summary ===\n"
            f"  Slice B FLIP cat-5->cat-12:    {slice_b_flipped} flipped, "
            f"{slice_b_skipped} skipped\n"
            f"  Slice C FLIP cat-12->cat-13:   {slice_c_flipped} flipped, "
            f"{slice_c_skipped} skipped\n"
            f"  Slice D DUAL ADD cat-13:       {slice_d_added} added, "
            f"{slice_d_skipped} skipped\n"
            f"  Slice E NEW creates cat-12:    {slice_e_created} created, "
            f"{slice_e_skipped} skipped, {slice_e_missing} missing"
        )

        # Post-apply cat-12 count for gate-1 projection
        cat12_count = session.scalars(
            select(EntityCategory).where(
                EntityCategory.category_id == cat12_id
            )
        ).all()
        print(
            f"\n  Post-apply cat-12 EntityCategory rows: {len(cat12_count)} "
            "(target >= 20 per kickoff §6)"
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
