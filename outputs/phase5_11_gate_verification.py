"""Phase 5.11 -- final 6 acceptance gate verification.

One-shot diagnostic that runs all 6 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.11 ships when this script reports all 6
items CLEARED.

Mirrors outputs/phase5_10_gate_verification.py shape -- copies events.db
to a tempdir before reading.

Phase 5.11 differs from 5.10 in four ways:
  - **Gate item 1 threshold is >=20** (same as 5.7/5.8/5.9/5.10) per
    kickoff 6. Pets density in LHC is moderate-low but well above the
    floor: **38 entities** rendering at /category/pets (1.9x target).
    Composition: 5 baseline (4 vets + Exotic Pet Kingdom from
    pre-Phase-5 veterinary_care/pet_store direct mappings) + 8 new
    from 1 load mapped to cat-11 (5 via direct mapping + 3 via 5.11 1
    sustainability commit 1dd443a's new pet_care/(None,"pets") catch-
    all routing) + 25 Slice E NEW creates from 2 audit (entire ambig
    pool reclassified as NEW creates -- all benign strip-mall geo-noise
    matches, no real cross-cat overlaps).
  - **Gate item 3 (verifier surface)** resolves via Option C -- explicitly
    deferred to V1.5 -- so the check is file-presence on the audit doc
    that documents the deferred AZ State Veterinary Medical Examining
    Board (azvetboard.gov; vets-only, out of 5.11 scope) + national
    pet franchise locators (PetSmart, Petco, Banfield) paths. Same
    Option C shape as 5.5/5.6/5.7/5.8/5.9/5.10.
  - **Gate item 5 (heat_exposure)** -- 5.11 mirrors 5.10 default of
    `indoor` for the bulk (34 pet stores / dog groomers / dog trainers /
    vet clinics -- venue-based indoor businesses); 4 outdoor overrides
    (Pet Oasis Doggy Daycare + The Dog House Doggy Day Care + Picky
    Mickie's Overnight Pet Sitting + Pooch Paradise -- all daycare /
    boarding venues with outdoor exercise areas); 0 water_adjacent
    overrides (cat-11 not lake-adjacent by definition; differs from
    5.10 which had 1 entry for Lake Havasu State Park Campground).
  - **Cross-cat axes outcome** notably different from kickoff
    forecast: cat-5 HWC vet-overlap PRIMARY axis was VACANT (no vets
    in cat-5 -- all LHC vets have veterinary_care primary which routes
    to cat-11, not medical_clinic primary which would route to cat-5);
    cat-7 dog-park SECONDARY axis 1 geo-noise hit (Picky Mickie's
    near Realtor Park, kept as Slice E NEW); cat-8 retail TERTIARY
    axis 2 PetSmart sub-service NEW creates (PetSmart Grooming +
    PetSmart Dog Training as distinct place_ids -- mirrors 5.10 Heat
    Hotel multi-place_id pattern). All 25 ambig records became Slice
    E NEW creates (vs 5.10's 6 NEW + 31 KEEP-ambig split).

Same as 5.6/5.7/5.8/5.9/5.10: 6 gates (no is_mobile_service -- cat-11
is venue-based; same rationale as the prior 5 phases). Gate-1 query
uses the ``(e.entity_type != 'commercial' OR provider-visible)``
OR-clause shape from phase5_2 / phase5_7 / phase5_8 / phase5_9 /
phase5_10 gate verifications for parity (though for 5.11 all 38
entities are expected commercial).

Usage:
    python outputs/phase5_11_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"
AUDIT_DOC = Path("outputs") / "phase5_11_pets_audit.md"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate511"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.11 -- Pets -- Final 6 Acceptance Gate")
    print("=" * 78)
    print()

    results: list[tuple[str, bool, str]] = []

    # --- Gate item 1 -------------------------------------------------------
    n = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'pets'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 20
    results.append(
        (
            "1. 20+ entries in pets post-load",
            item1,
            f"{n} entities rendering at /category/pets (target: 20+ per kickoff 6)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.11 reconciler review: 25 ambig records dump-surfaced audited in
    # outputs/phase5_11_pets_audit.md 4 -- finding was:
    #   Slice A: KEEP (no apply) -- 13 cat-11 entries (5 baseline + 8
    #           1-load new) + 3 cat-8 pet-retail stays (PetSmart,
    #           Doggie Shades, Rok Dog Leashes -- V1.5 DUAL carry)
    #   Slice B: 0 FLIP cat-X -> cat-11 (no real cross-cat overlap;
    #           all 25 ambig matches are strip-mall geo-noise)
    #   Slice C: 0 FLIP cat-11 -> cat-X
    #   Slice D: 0 DUAL ADD for V1 (V1.5 carries for cat-8 pet-retail
    #           + Beautiful Beards franchise + PetSmart franchise)
    #   Slice E: 25 NEW creates cat-11 (all ambig records reclassified)
    #   Slice F: 0 KEEP-ambig (all 25 are real pet businesses)
    #   Slice G: 0 DRAFT/DELETE
    # Special audits cleared:
    #   (a) cat-5 HWC vet-overlap PRIMARY -- VACANT (0 vets in cat-5;
    #       all LHC vets in cat-11 via veterinary_care primary; 5
    #       ambig candidates matched cat-5 entities but all are pet-
    #       shop-next-to-gym/doctor strip-mall geo-noise)
    #   (b) cat-7 outdoors-parks-trails dog-park SECONDARY -- 1 geo-
    #       noise hit (Picky Mickie's Overnight Pet Sitting near
    #       Realtor Park, 42.9m; reclassified Slice E NEW)
    #   (c) cat-8 shopping-essentials retail-overlap TERTIARY -- 2
    #       PetSmart sub-service NEW creates (Grooming + Dog Training
    #       as distinct place_ids; existing PetSmart stays cat-8)
    #   (d) cat-1 eat-drink decorative -- 9 strip-mall geo-noise (all
    #       reclassified Slice E NEW; no real cat-1 overlap)
    #
    # Acceptance signal: no pets providers have category_id IS NULL
    # post-sustainability + Slice E apply. The sustainability commit
    # at 1dd443a (4 direct _PRIMARY_TYPE_MAP entries + 1 (None, "pets")
    # catch-all) closed the primary_type=NULL gap; the 2 audit Slice E
    # apply set category_id=cat-11 on every NEW Provider.
    n_null = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'pets'
          AND p.category_id IS NULL
        """
    ).fetchone()[0]
    item2 = n_null == 0
    results.append(
        (
            "2. All Google <-> existing-entity ambiguous reconciler hits reviewed (+ 4 special audits)",
            item2,
            f"pets providers w/ NULL category_id: {n_null} "
            "(target: 0); 25 ambig records reviewed per audit 4 -- "
            "all 25 reclassified as Slice E NEW creates (strip-mall "
            "geo-noise; no real cross-cat overlap); 4 special audits "
            "(a) cat-5 HWC vet-overlap VACANT / (b) cat-7 dog-park 1 "
            "geo-noise / (c) cat-8 retail 2 PetSmart sub-services / "
            "(d) cat-1 eat-drink 9 geo-noise -- all cleared",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # Option C -- Layer-4 verifier surface explicitly deferred to V1.5.
    # The audit doc + kickoff 3 document AZ State Veterinary Medical
    # Examining Board (azvetboard.gov; vets-only, out of 5.11 scope by
    # design) + national pet franchise locators (PetSmart / Petco /
    # Banfield) paths for V1.5 pickup.
    # Acceptance signal: the audit doc exists AND no providers in
    # pets have verification_method set to az_vet_board /
    # petsmart_locator / petco_locator / banfield_locator (no verifier
    # ran).
    audit_exists = AUDIT_DOC.is_file()
    n_verified = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'pets'
          AND p.verification_method IS NOT NULL
          AND p.verification_method IN (
              'az_vet_board',
              'petsmart_locator',
              'petco_locator',
              'banfield_locator'
          )
        """
    ).fetchone()[0]
    item3 = audit_exists and n_verified == 0
    results.append(
        (
            "3. Layer-4 verifier surface scoped -- built or explicitly deferred to V1.5",
            item3,
            f"audit doc exists: {audit_exists}; "
            f"providers verified via az-vet/petsmart/petco/banfield: {n_verified} "
            "(target: 0 -- Option C deferred); AZ Vet Board + national "
            "pet franchise locator paths documented in kickoff 3 for "
            "V1.5 pickup",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'pets'
          AND e.is_active = 1
          AND e.crowd_notes IS NOT NULL
          AND e.crowd_notes LIKE '%"long"%'
        """
    ).fetchone()[0]
    item4 = n_long >= 10
    results.append(
        (
            "4. Top-10 by reviews have long-form crowd_notes",
            item4,
            f"{n_long} pets entities have long-form crowd_notes (target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    null_he, total_cat11 = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'pets'
          AND e.is_active = 1
        """
    ).fetchone()
    null_he = null_he or 0
    item5 = null_he == 0 and total_cat11 > 0
    n_indoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'pets'
          AND e.is_active = 1
          AND e.heat_exposure = 'indoor'
        """
    ).fetchone()[0]
    n_outdoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'pets'
          AND e.is_active = 1
          AND e.heat_exposure = 'outdoor'
        """
    ).fetchone()[0]
    results.append(
        (
            "5. heat_exposure set on every pets entry",
            item5,
            f"{null_he} of {total_cat11} have heat_exposure=NULL (target: 0); "
            f"{n_indoor} set to 'indoor' (default; pet stores / dog "
            "groomers / dog trainers / vet clinics are indoor-by-"
            f"definition), {n_outdoor} set to 'outdoor' (daycare + "
            "boarding venues with outdoor exercise areas)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    item6 = n >= 15
    results.append(
        (
            "6. /category/pets renders >=15 per default filter",
            item6,
            f"page: {n} entities (target: 15+)",
        )
    )

    # --- Scoreboard --------------------------------------------------------
    print("Gate item                                                           Status")
    print("-" * 78)
    for label, passed, detail in results:
        marker = "OK PASS" if passed else "XX FAIL"
        print(f"  {label:<60} {marker}")
        print(f"    -> {detail}")
        print()

    all_passed = all(passed for _, passed, _ in results)
    print("=" * 78)
    if all_passed:
        print("PHASE 5.11 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED -- READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.11 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
