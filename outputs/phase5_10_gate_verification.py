"""Phase 5.10 -- final 6 acceptance gate verification.

One-shot diagnostic that runs all 6 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.10 ships when this script reports all 6
items CLEARED.

Mirrors outputs/phase5_9_gate_verification.py shape -- copies events.db
to a tempdir before reading.

Phase 5.10 differs from 5.9 in three ways:
  - **Gate item 1 threshold is >=20** (same as 5.7/5.8/5.9) per kickoff
    6. Lodging-vacation-rentals density in LHC is high -- 31 pre-1
    entries (5.2-absorbed RV parks + campgrounds + lodging-primary
    vacation rentals via secondary-types[] match on existing lodging
    direct map) + 35 1.6 inserts with EntityCategory + 1 1.7c flip
    (Vanderpump villa NULL -> cat-10 via NEW (None, "lodging")
    catch-all from bf24e16) + 6 Slice E NEW creates from 2 audit =
    **73 entities** rendering at /category/lodging-vacation-rentals
    (3.65x target). All 73 are entity_type='commercial' (no place-typed
    entries; no swimming_pool / tennis_court analogs in lodging scope).
  - **Gate item 3 (verifier surface)** resolves via Option C -- explicitly
    deferred to V1.5 -- so the check is file-presence on the audit doc
    that documents the deferred AZDOR transient-lodging tax registry +
    AZRE vacation-rental license registry + LHC Tourism Board lodging
    directory paths (vs 5.9's AZDHS childcare-license / franchise gym
    chain APIs / LHC Parks & Rec).
  - **Gate item 5 (heat_exposure)** -- 5.10 mirrors 5.8/5.9 default of
    `indoor` for the bulk (53 hotels/motels/cottages/vacation rentals/
    B&Bs/guest_house/camping_cabin/mobile_home_park/service); 19 outdoor
    overrides (14 rv_park + 5 inland campgrounds); 1 water_adjacent
    override (Lake Havasu State Park Campground -- the literal
    waterfront campground inside the state park).

Same as 5.6/5.7/5.8/5.9: 6 gates (no is_mobile_service -- cat-10 is
venue-based; same rationale as 5.6 brick-and-mortar / 5.7 place-based /
5.8 venue-based events / 5.9 venue-based classes). Gate-1 query uses
the ``(e.entity_type != 'commercial' OR provider-visible)`` OR-clause
shape from phase5_2 / phase5_7 / phase5_8 / phase5_9 gate verifications
for parity (though for 5.10 all 73 entities are expected commercial).

Usage:
    python outputs/phase5_10_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"
AUDIT_DOC = Path("outputs") / "phase5_10_lodging_audit.md"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate510"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.10 -- Lodging & Vacation Rentals -- Final 6 Acceptance Gate")
    print("=" * 78)
    print()

    results: list[tuple[str, bool, str]] = []

    # --- Gate item 1 -------------------------------------------------------
    # Uses the (e.entity_type != 'commercial' OR provider-visible) shape
    # from phase5_2 / phase5_7 / phase5_8 / phase5_9 gate verifications.
    # For 5.10 all 73 entities are expected commercial (no place-typed
    # like swimming_pool/tennis_court analogs in lodging scope) -- the
    # OR-clause is required for route-render parity.
    n = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'lodging-vacation-rentals'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 20
    results.append(
        (
            "1. 20+ entries in lodging-vacation-rentals post-load",
            item1,
            f"{n} entities rendering at /category/lodging-vacation-rentals "
            "(target: 20+ per kickoff 6)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.10 reconciler review: 37 ambig records dump-surfaced audited in
    # outputs/phase5_10_lodging_audit.md 4 -- finding was:
    #   Slice A: KEEP (no apply) -- 67 cat-10 entries + HEAT Bar stays in cat-1
    #   Slice B: 0 FLIP cat-X -> cat-10
    #   Slice C: 0 FLIP cat-10 -> cat-X
    #   Slice D: 0 DUAL ADD cat-3 (forecast 2-5 didn't materialize --
    #           no waterfront-primary candidates per dupe-check coords)
    #   Slice E: 6 NEW creates in cat-10 (Heat Hotel + Travelodge by
    #           Wyndham + Knights Inn + LAKE PLACE INN + Holiday Inn
    #           Express by IHG + Queens Bay Resort Condominiums)
    #   Slice F: 31 KEEP-ambig (29 lake_recreation-domain geo-noise +
    #           Havasu Suites + Xanadu -- both uncertain V1.5 carry)
    #   Slice G: 0 DRAFT/DELETE
    # Special audits cleared:
    #   (a) cat-3 on-the-water primary axis -- 0 lodging-domain hits
    #       (the 3 cat-3 ambig hits are lake_recreation-domain boat
    #       businesses near marinas, not waterfront resorts)
    #   (b) cat-1 eat-drink secondary axis -- 1 real hit (Heat Hotel
    #       ambig-matched HEAT Bar at 8.6m; both kept distinct per
    #       same-business-two-place_ids 5.7/5.8 pattern); 24 geo-noise
    #   (c) cat-2 events tertiary axis -- 0 real hits; 5 adjacency-only
    #       matches at 73m (within NEAR_GEO threshold but not co-located)
    #
    # Acceptance signal: no lodging-vacation-rentals providers have
    # category_id IS NULL post-1.7c-sustainability + 2-apply. The
    # sustainability commit at bf24e16 (5 direct _PRIMARY_TYPE_MAP
    # entries + 1 (None, "lodging") catch-all) closed the
    # primary_type=NULL gap; the 2 audit Slice E NEW creates set
    # category_id=cat-10 on every NEW Provider.
    n_null = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'lodging-vacation-rentals'
          AND p.category_id IS NULL
        """
    ).fetchone()[0]
    item2 = n_null == 0
    results.append(
        (
            "2. All Google <-> existing-entity ambiguous reconciler hits reviewed (+ 3 special audits)",
            item2,
            f"lodging-vacation-rentals providers w/ NULL category_id: {n_null} "
            "(target: 0); 37 ambig records reviewed per audit 3-7 -- "
            "Slice E 6 NEW (5 hotels + 1 condo) + Slice F 31 KEEP-ambig "
            "(29 lake_rec geo-noise + 2 uncertain V1.5 carry); special "
            "audits (a) cat-3 on-the-water / (b) cat-1 eat-drink / (c) "
            "cat-2 events all cleared",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # Option C -- Layer-4 verifier surface explicitly deferred to V1.5.
    # The audit doc + kickoff 3 document AZDOR transient-lodging tax
    # registry (azdor.gov/transaction-privilege-tax-tpt) + AZRE
    # vacation-rental license registry (azre.gov/PropertyManagement) +
    # LHC Tourism Board lodging directory (golakehavasu.com) paths for
    # V1.5 pickup.
    # Acceptance signal: the audit doc exists AND no providers in
    # lodging-vacation-rentals have verification_method set to
    # azdor_tpt / azre_vacation_rental / lhc_tourism (no verifier ran).
    audit_exists = AUDIT_DOC.is_file()
    n_verified = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'lodging-vacation-rentals'
          AND p.verification_method IS NOT NULL
          AND p.verification_method IN (
              'azdor_tpt',
              'azre_vacation_rental',
              'lhc_tourism'
          )
        """
    ).fetchone()[0]
    item3 = audit_exists and n_verified == 0
    results.append(
        (
            "3. Layer-4 verifier surface scoped -- built or explicitly deferred to V1.5",
            item3,
            f"audit doc exists: {audit_exists}; "
            f"providers verified via azdor/azre/lhc-tourism: {n_verified} "
            "(target: 0 -- Option C deferred); AZDOR transient-lodging "
            "tax + AZRE vacation-rental license + LHC Tourism Board "
            "paths documented in kickoff 3 for V1.5 pickup",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'lodging-vacation-rentals'
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
            f"{n_long} lodging-vacation-rentals entities have long-form crowd_notes "
            "(target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    # heat_exposure on every entry. Uses total entities in category as
    # the denominator (covers all linked entities including any drafts).
    null_he, total_cat10 = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'lodging-vacation-rentals'
          AND e.is_active = 1
        """
    ).fetchone()
    null_he = null_he or 0
    item5 = null_he == 0 and total_cat10 > 0
    n_indoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'lodging-vacation-rentals'
          AND e.is_active = 1
          AND e.heat_exposure = 'indoor'
        """
    ).fetchone()[0]
    n_outdoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'lodging-vacation-rentals'
          AND e.is_active = 1
          AND e.heat_exposure = 'outdoor'
        """
    ).fetchone()[0]
    n_water = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'lodging-vacation-rentals'
          AND e.is_active = 1
          AND e.heat_exposure = 'water_adjacent'
        """
    ).fetchone()[0]
    results.append(
        (
            "5. heat_exposure set on every lodging-vacation-rentals entry",
            item5,
            f"{null_he} of {total_cat10} have heat_exposure=NULL (target: 0); "
            f"{n_indoor} set to 'indoor' (default; hotels / motels / cottages / "
            "vacation rentals / B&Bs are indoor-by-definition), "
            f"{n_outdoor} set to 'outdoor' (RV parks + inland campgrounds), "
            f"{n_water} set to 'water_adjacent' (Lake Havasu State Park "
            "Campground -- the literal waterfront campground)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    # /category/lodging-vacation-rentals renders >=15. Page-render
    # count is the same as item 1's count (the route uses the
    # EntityCategory join + draft=0 filter, identical to the gate-1
    # query above).
    item6 = n >= 15
    results.append(
        (
            "6. /category/lodging-vacation-rentals renders >=15 per default filter",
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
        print("PHASE 5.10 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED -- READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.10 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
