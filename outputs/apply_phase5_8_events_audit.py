"""Apply the Phase 5.8 events data-quality audit decisions.

Mirrors outputs/apply_phase5_7_parks_audit.py but expanded for 5.8's
substantially larger §2 surface: 15 NEW entity creates (Slice A) + 2
cross-cat moves (Slice B) + 1 DRAFT (Slice C). The NEW creates are the
key differentiator vs 5.7 — 5.8's load ambig-skipped 22 candidates and
the audit decided 15 of them deserve cat-2 placement (the matched
ambig entities are distinct businesses geo-adjacent to existing
entities).

Source of truth for the decisions:
``outputs/phase5_8_events_audit.md`` §4 Slice A (FLIPs) + Slice B
(cross-cat moves) + Slice C (DRAFT).

Strategy:
- For NEW creates (Slice A + Slice C): construct Provider via
  ``places_load.row_to_provider_kwargs`` from the enrichment cache;
  call ``create_provider_and_entity`` which dual-writes Entity +
  Location + EntityCategory + ContactPoint + SourceEvidence. Override
  ``Entity.entity_type='place'`` post-create for art_gallery /
  history_museum primaries (per 5.8 §1 sustainability commit's
  commercial-vs-place split).
- For cross-cat moves (Slice B): look up existing entity by name,
  DELETE old EntityCategory, INSERT new EntityCategory(cat-2,
  is_primary=True), update Provider.category_id. For Altitude
  Trampoline Park, also set Provider.draft=False (un-DRAFT from cat-7).
- For DRAFT (Slice C): same as Slice A NEW create but with
  Provider.draft=True. art_gallery → place, so renders even drafted
  per the gate-1 OR-clause.

Usage:
    python outputs/apply_phase5_8_events_audit.py --dry-run
    python outputs/apply_phase5_8_events_audit.py

Net effect:
    /category/events                 : 2 -> ~21 (15 NEW + 2 cross-cat +
                                                  1 DRAFT + 1 §1 insert
                                                  already there)
    /category/on-the-water           : -1 (Lake Havasu Museum of History
                                            moves out)
    /category/outdoors-parks-trails  : -1 + un-DRAFT (Altitude
                                        Trampoline moves out; 26 of
                                        former 27 renders still in cat-7
                                        — Altitude was DRAFTed in 5.7 §2
                                        so didn't render anyway, net 26
                                        rendering cat-7 stays unchanged)

Re-run safety: idempotent. NEW creates dedupe on google_place_id; if a
candidate place_id is already a Provider row (from a prior run of this
script or a manual flush), the script SKIPs the create. Cross-cat
moves DELETE + INSERT same row (net updated_at). DRAFT marker no-op'd
if already draft=True.

DB-write — stop FastAPI dev server first to avoid events.db lock per
the 5.4 / 5.5 / 5.6 / 5.7 close-out gotcha.
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

# Slice A — 15 NEW entity creates in cat-2 (high-confidence FLIPs).
# Listed by candidate name (per the §1 ambig pool); the script resolves
# each name to a place_id via the enrichment cache at runtime
# (``_pid_for_name``). Names taken verbatim from the dump-script
# output's structured records. Order matches the audit doc §4 Slice A
# table.
SLICE_A_NEW_FLIPS_BY_NAME: list[str] = [
    "Star Cinemas",                              # movie_theater, 814r
    "Havasu Art Center",                         # art_gallery, 8r
    "The Q Art Gallery",                         # art_gallery, 9r
    "Christine's Fine Art LLC",                  # art_gallery, 4r
    "Jaque Meng",                                # art_gallery, no reviews
    "Tyanna Renee Gallery",                      # art_gallery, no reviews
    "American Legion",                           # association, 140r — event venues label
    "Realtor Convention Center",                 # real_estate_agency, 4r — name explicit
    "AZ Party Express",                          # service, 11r — event venues label
    "Four Quarters Amusements",                  # manufacturer/arcade, 46r
    "Lake Havasu, AZ Elks Lodge #2399",          # association, 388r — name real, label noisy
    "Ru Art Gallery and Boutique",               # clothing_store, 18r — name says Art Gallery
    "Quest Realm",                               # store, 100r — gaming venue
    "WORCS Racing",                              # race_course, 1r — event venues label
    "High End Productions Llc",                  # None primary, 2r — event venues label
                                                  # NOTE: dump preserves source case "Llc"
    # Added 2026-05-17 post-first-apply correction: the audit doc's
    # Slice B-1 misclassified this as a cat-6 → cat-2 move under the
    # assumption that an existing "Lake Havasu Museum of History"
    # entity was in cat-6 (per the kickoff §2 framing). DB query
    # confirmed no such entity exists — the 5.7 §1 ambig candidate
    # was never inserted ("0 flips needed" per 5.7 close-out §4
    # meant the AMBIG candidates including LH Museum of History
    # stayed unmapped, not that they FLIPped to cat-2). 5.8's
    # candidate "Lake Havasu Museum of History & Havasu Rocks"
    # (history_museum primary, 213 reviews) is a NEW entity.
    "Lake Havasu Museum of History & Havasu Rocks",
]

# Slice B-1 — REMOVED.
#
# The first apply run revealed the audit doc's Slice B-1 premise was
# wrong: there was no existing "Lake Havasu Museum of History" entity
# in cat-6 to FLIP. The 5.7 §1 ambig pool included a museum candidate
# but it was KEPT as ambig ("0 flips needed" per 5.7 close-out §4), so
# no DB row existed pre-5.8. The 5.8 candidate has been re-classified
# as a NEW create (added to SLICE_A_NEW_FLIPS_BY_NAME above as
# "Lake Havasu Museum of History & Havasu Rocks").
SLICE_B1_CROSS_CAT_MOVE_BY_NAME: dict[str, str] = {}

# Slice B-2 — 1 cross-cat MOVE + un-DRAFT (cat-7 → cat-2).
# Altitude Trampoline Park was DRAFTed in cat-7 per 5.7 §2 pending the
# 5.8 lane. 5.8 IS that lane.
SLICE_B2_CROSS_CAT_MOVE_AND_UNDRAFT_BY_NAME: dict[str, str] = {
    "Altitude Trampoline Park": "events",
}

# Slice C — 1 DRAFT to cat-2.
# Simply Savage Designs has art_gallery primary but name suggests
# design/print shop; 1 review. DRAFT for operator review; place-typed
# (art_gallery → place) so renders even drafted.
SLICE_C_DRAFT_BY_NAME: list[str] = [
    "Simply Savage Designs",
]

# Primary types that should be entity_type='place' (per 5.8 §1
# sustainability commit at 0b426e1).
PLACE_TYPED_PRIMARIES: frozenset[str] = frozenset({
    "art_gallery",
    "museum",
    "history_museum",
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


def _create_new_entity_in_cat2(
    session,
    row: dict,
    cat2_id: int,
    *,
    draft: bool = False,
) -> tuple[Provider, Entity] | None:
    """Construct Provider from enriched row + call create_provider_and_entity.

    Returns (provider, entity) on success; None if a Provider with the
    same google_place_id already exists (idempotent re-run skip).
    """
    pid = row["place_id"]
    existing = session.scalars(
        select(Provider).where(Provider.google_place_id == pid)
    ).first()
    if existing is not None:
        return None  # already created (idempotent skip)

    kwargs = row_to_provider_kwargs(row)
    kwargs["category_id"] = cat2_id
    kwargs["draft"] = draft

    prov = Provider(**kwargs)
    session.add(prov)
    prov, ent = create_provider_and_entity(session, prov)

    # Override entity_type for art_gallery / museum primaries per the
    # 5.8 sustainability commit (0b426e1) commercial-vs-place split.
    primary = (row.get("primary_type") or "").lower()
    if primary in PLACE_TYPED_PRIMARIES:
        ent.entity_type = ENTITY_TYPE_PLACE
    return prov, ent


def _move_entity_to_cat(
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


def _un_draft_provider(session, entity_id: str) -> bool:
    """Set Provider.draft=False for the entity. Returns True on change."""
    prov = session.scalars(
        select(Provider).where(Provider.entity_id == entity_id)
    ).first()
    if prov is None:
        return False
    if not prov.draft:
        return False  # already not-draft
    prov.draft = False
    prov.updated_at = _utc_now_naive()
    return True


def _set_draft_provider(session, entity_id: str) -> bool:
    """Set Provider.draft=True for the entity. Returns True on change."""
    prov = session.scalars(
        select(Provider).where(Provider.entity_id == entity_id)
    ).first()
    if prov is None:
        return False
    if prov.draft:
        return False  # already draft
    prov.draft = True
    prov.updated_at = _utc_now_naive()
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
        for needed in ("events",):
            if needed not in slug_to_id:
                raise RuntimeError(f"missing category slug: {needed}")
        cat2_id = slug_to_id["events"]

        # Slice A — 15 NEW entity creates
        print("\n=== Slice A: 15 NEW entity creates in cat-2 ===")
        slice_a_created = 0
        slice_a_skipped = 0
        slice_a_missing = 0
        for target_name in SLICE_A_NEW_FLIPS_BY_NAME:
            pid = _pid_for_name(enrichment, target_name)
            if pid is None:
                print(f"  [MISSING] enrichment row not found by name: {target_name!r}")
                slice_a_missing += 1
                continue
            row = enrichment[pid]
            result = _create_new_entity_in_cat2(session, row, cat2_id)
            if result is None:
                print(f"  [skip] already exists: {target_name!r}")
                slice_a_skipped += 1
            else:
                prov, ent = result
                print(
                    f"  [create] {ent.name!r:55s} entity_type={ent.entity_type} "
                    f"primary={row.get('primary_type')!r}"
                )
                slice_a_created += 1
        print(
            f"  Slice A summary: {slice_a_created} created, "
            f"{slice_a_skipped} skipped, {slice_a_missing} missing"
        )
        if slice_a_missing > 0:
            print(
                "  [WARNING] missing names indicate enrichment cache lookup "
                "failure — verify name spellings against the dump records "
                "in outputs/phase5_8_ambig_audit_data.json before applying."
            )

        # Slice B-1 — 1 cross-cat move (cat-6 → cat-2)
        print("\n=== Slice B-1: cross-cat move (cat-6 → cat-2) ===")
        slice_b1_moved = 0
        for name, target_slug in SLICE_B1_CROSS_CAT_MOVE_BY_NAME.items():
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(f"  [skip] not found: {name!r}")
                continue
            _move_entity_to_cat(session, ent.id, slug_to_id[target_slug])
            print(f"  [move] {name!r} -> {target_slug}")
            slice_b1_moved += 1

        # Slice B-2 — 1 cross-cat move + un-DRAFT (cat-7 → cat-2)
        print("\n=== Slice B-2: cross-cat move + un-DRAFT (cat-7 → cat-2) ===")
        slice_b2_moved = 0
        for name, target_slug in SLICE_B2_CROSS_CAT_MOVE_AND_UNDRAFT_BY_NAME.items():
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(f"  [skip] not found: {name!r}")
                continue
            _move_entity_to_cat(session, ent.id, slug_to_id[target_slug])
            un_drafted = _un_draft_provider(session, ent.id)
            print(
                f"  [move+undraft] {name!r} -> {target_slug} "
                f"(provider un-drafted={un_drafted})"
            )
            slice_b2_moved += 1

        # Slice C — 1 DRAFT new entity create
        print("\n=== Slice C: 1 DRAFT new entity create ===")
        slice_c_created = 0
        for target_name in SLICE_C_DRAFT_BY_NAME:
            pid = _pid_for_name(enrichment, target_name)
            if pid is None:
                print(f"  [skip] enrichment row not found by name: {target_name!r}")
                continue
            row = enrichment[pid]
            result = _create_new_entity_in_cat2(session, row, cat2_id, draft=True)
            if result is None:
                print(f"  [skip] already exists: {target_name!r}")
                # idempotent: ensure draft=True even if entity exists
                existing = session.scalars(
                    select(Provider).where(Provider.google_place_id == pid)
                ).first()
                if existing is not None and existing.entity_id:
                    _set_draft_provider(session, existing.entity_id)
            else:
                prov, ent = result
                print(
                    f"  [create-draft] {ent.name!r:55s} entity_type={ent.entity_type} "
                    f"draft={prov.draft}"
                )
                slice_c_created += 1

        print(
            "\n=== Summary ===\n"
            f"  Slice A new creates: {slice_a_created} (skipped {slice_a_skipped})\n"
            f"  Slice B-1 cat-6→cat-2 moves: {slice_b1_moved}\n"
            f"  Slice B-2 cat-7→cat-2 moves+undraft: {slice_b2_moved}\n"
            f"  Slice C new DRAFT: {slice_c_created}"
        )

        # Post-apply cat-2 count for gate-1 projection
        cat2_count = session.scalars(
            select(EntityCategory).where(EntityCategory.category_id == cat2_id)
        ).all()
        print(f"\n  Post-apply cat-2 EntityCategory rows: {len(cat2_count)}")

        if args.dry_run:
            print("\n[dry-run] rolling back; no DB writes.")
            session.rollback()
        else:
            session.commit()
            print("\n[apply] committed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
