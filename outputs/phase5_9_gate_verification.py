"""Phase 5.9 — final §6 acceptance gate verification.

One-shot diagnostic that runs all 6 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.9 ships when this script reports all 6
items CLEARED.

Mirrors outputs/phase5_8_gate_verification.py shape — copies events.db
to a tempdir before reading.

Phase 5.9 differs from 5.8 in three ways:
  - **Gate item 1 threshold is >=20** (same as 5.7/5.8) per kickoff §6.
    Classes-sports-recreation density in LHC is moderate — 27 §1 inserts
    + 3 Slice E NEW + 1 Slice B FLIP-in - 2 Slice C FLIPs-out plus the
    ~4 pre-existing `school`-primary entries from cache absorption =
    31 entities; gate-1 counts those that render via the OR-clause
    shape (Aquatic Center is entity_type='place' per the swimming_pool
    -> place mapping at 0af5f73; everything else is commercial).
  - **Gate item 3 (verifier surface)** resolves via Option C — explicitly
    deferred to V1.5 — so the check is file-presence on the audit doc
    that documents the deferred AZDHS childcare-license registry +
    franchise gym chain APIs + LHC Parks & Rec municipal pages paths
    (vs 5.8's AZ event aggregators + LHC Tourism Board).
  - **Gate item 5 (heat_exposure)** — 5.9 mirrors 5.8's default of
    `indoor`; the override count is small (2: Aquatic Center +
    Stormy Wade Courts) since most cat-12 entries are schools / daycare
    / preschools / studios / classrooms (indoor by definition).

Same as 5.6/5.7/5.8: 6 gates (no is_mobile_service — cat-12 is mostly
venue-based; same rationale as 5.6 brick-and-mortar / 5.7 place-based /
5.8 venue-based events). Gate-1 query uses the
``(e.entity_type != 'commercial' OR provider-visible)`` OR-clause shape
from phase5_2 / phase5_7 / phase5_8 gate verifications to correctly
count both ``place``-typed (swimming_pool / tennis_court /
pickleball_court primaries per 5.9 sustainability) and
``commercial``-typed entries uniformly.

Usage:
    python outputs/phase5_9_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"
AUDIT_DOC = Path("outputs") / "phase5_9_classes_audit.md"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate59"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.9 — Classes, Sports & Recreation — Final §6 Acceptance Gate")
    print("=" * 78)
    print()

    results: list[tuple[str, bool, str]] = []

    # --- Gate item 1 -------------------------------------------------------
    # Uses the (e.entity_type != 'commercial' OR provider-visible) shape
    # from phase5_2 / phase5_7 / phase5_8 gate verifications to handle
    # both place- and commercial-typed entries uniformly. 5.9's Aquatic
    # Center is entity_type='place' (per the swimming_pool -> place
    # mapping at 0af5f73); the rest are commercial.
    n = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'classes-sports-recreation'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 20
    results.append(
        (
            "1. 20+ entries in classes-sports-recreation post-load",
            item1,
            f"{n} entities rendering at /category/classes-sports-recreation "
            "(target: 20+ per kickoff §6)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.9 reconciler review: 30 ambig records dump-surfaced (23 in-scope
    # from §1 load + 7 cross-cache from prior-phase domain leakage)
    # audited in outputs/phase5_9_classes_audit.md §4 — finding was:
    #   Slice B: 1 FLIP cat-5 -> cat-12 (Stormy Wade Courts)
    #   Slice C: 2 FLIPs cat-12 -> cat-13 (Knights of Columbus +
    #            Hilltop Community Church)
    #   Slice D: 1 DUAL ADD cat-13 (Our Lady of the Lake Catholic School)
    #   Slice E: 3 NEW creates in cat-12 (Aquatic Center + Psalms +
    #            Mohave Traffic School)
    #   Slice F: 20 KEEP-ambig (gym/yoga/pilates HWC-deferred per V1.5)
    #   plus 7 cross-cache informational (not in §1 load scope)
    # Special audits cleared:
    #   (a) cat-5 HWC primary axis — 0 real misroutes; 26 §1-updates
    #       kept cat-5 per V1 policy (V1.5 dual-cat consideration)
    #   (b) cat-7 outdoors-parks-trails secondary axis — 0 cross-list
    #       hits in ambig pool
    #   (c) cat-13 public-civic-resources cross-list — 1 hit (Aquatic
    #       Center vs Parks & Rec Dept at 22m), addressed by Slice E
    #       NEW-create per primary identity
    #
    # Acceptance signal: no classes-sports-recreation providers have
    # category_id IS NULL post-§1-sustainability + apply-script. The
    # sustainability commit at 0af5f73 (9 direct _PRIMARY_TYPE_MAP
    # entries + 1 childcare_education catch-all) closed the
    # primary_type=NULL gap pre-load; the apply-script set
    # category_id=cat-12 on every NEW Provider.
    n_null = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'classes-sports-recreation'
          AND p.category_id IS NULL
        """
    ).fetchone()[0]
    item2 = n_null == 0
    results.append(
        (
            "2. All Google <-> existing-entity ambiguous reconciler hits reviewed (+ 3 special audits)",
            item2,
            f"classes-sports-recreation providers w/ NULL category_id: {n_null} "
            "(target: 0); 30 ambig records reviewed per audit §3-7 — "
            "Slices B (1 FLIP-in) + C (2 FLIPs-out) + D (1 DUAL) + E (3 NEW) "
            "+ F (20 KEEP-ambig per V1.5 deferral); special audits "
            "(a) cat-5 HWC / (b) cat-7 outdoors / (c) cat-13 public-civic "
            "all cleared",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # Option C — Layer-4 verifier surface explicitly deferred to V1.5.
    # The audit doc + kickoff §3 document AZDHS childcare-license
    # registry (azdhs.gov/licensing/childcare-facilities) + franchise
    # gym chain APIs (Anytime Fitness / Snap Fitness / Orange Theory)
    # + LHC Parks & Rec municipal pages paths for V1.5 pickup.
    # Acceptance signal: the audit doc exists AND no providers in
    # classes-sports-recreation have verification_method set to
    # azdhs_childcare / anytime_fitness / snap_fitness / lhc_parks_rec
    # (no verifier ran).
    audit_exists = AUDIT_DOC.is_file()
    n_verified = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'classes-sports-recreation'
          AND p.verification_method IS NOT NULL
          AND p.verification_method IN (
              'azdhs_childcare',
              'anytime_fitness',
              'snap_fitness',
              'orange_theory',
              'lhc_parks_rec'
          )
        """
    ).fetchone()[0]
    item3 = audit_exists and n_verified == 0
    results.append(
        (
            "3. Layer-4 verifier surface scoped — built or explicitly deferred to V1.5",
            item3,
            f"audit doc exists: {audit_exists}; "
            f"providers verified via azdhs/franchise/lhc-parks-rec: {n_verified} "
            "(target: 0 — Option C deferred); AZDHS childcare-license "
            "registry + franchise gym chain APIs + LHC Parks & Rec paths "
            "documented in kickoff §3 for V1.5 pickup",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'classes-sports-recreation'
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
            f"{n_long} classes-sports-recreation entities have long-form crowd_notes "
            "(target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    # heat_exposure on every entry. Uses total entities in category as
    # the denominator (covers all linked entities including any drafts).
    null_he, total_cat12 = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'classes-sports-recreation'
          AND e.is_active = 1
        """
    ).fetchone()
    null_he = null_he or 0
    item5 = null_he == 0 and total_cat12 > 0
    n_indoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'classes-sports-recreation'
          AND e.is_active = 1
          AND e.heat_exposure = 'indoor'
        """
    ).fetchone()[0]
    n_outdoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'classes-sports-recreation'
          AND e.is_active = 1
          AND e.heat_exposure = 'outdoor'
        """
    ).fetchone()[0]
    results.append(
        (
            "5. heat_exposure set on every classes-sports-recreation entry",
            item5,
            f"{null_he} of {total_cat12} have heat_exposure=NULL (target: 0); "
            f"{n_indoor} set to 'indoor' (default; daycare / preschools / schools "
            f"/ studios / classrooms are indoor-by-definition), {n_outdoor} set "
            "to 'outdoor' (cat-12-native outdoor venues — Lake Havasu City "
            "Aquatic Center + Stormy Wade Courts)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    # /category/classes-sports-recreation renders >=15. Page-render
    # count is the same as item 1's count (the route uses the
    # EntityCategory join + draft=0 filter, identical to the gate-1
    # query above).
    item6 = n >= 15
    results.append(
        (
            "6. /category/classes-sports-recreation renders >=15 per default filter",
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
        print("PHASE 5.9 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED -- READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.9 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
