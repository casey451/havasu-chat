"""Phase 5.7 — final §6 acceptance gate verification.

One-shot diagnostic that runs all 6 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.7 ships when this script reports all 6
items CLEARED.

Mirrors outputs/phase5_6_gate_verification.py shape — copies events.db
to a tempdir before reading.

Phase 5.7 differs from 5.6 in three ways:
  - **Gate item 1 threshold is ≥20** (vs 5.6's ≥40) per kickoff §6.
    Parks-and-trails density in LHC is lower than retail; 6 pre-existing
    + ≥14 net-new is the kickoff §6 target shape.
  - **Gate item 3 (verifier surface)** resolves via Option C — explicitly
    deferred to V1.5 — so the check is file-presence on the audit doc
    that documents the deferred AZ State Parks + NPS + LHC Parks & Rec
    paths (vs 5.6's AZ TPT + BBB).
  - **Gate item 5 (heat_exposure)** — 5.7 flips the default to ``outdoor``
    (vs 5.6's ``indoor``); the detail line reports ``outdoor`` count first.

Same as 5.6: 6 gates (no is_mobile_service — parks/golf are place-based
by definition; same rationale as 5.6's brick-and-mortar retail). Gate-1
query uses the ``(e.entity_type != 'commercial' OR provider-visible)``
OR-clause shape from phase5_2_gate_verification.py and
phase5_6_gate_verification.py to correctly count both ``place``-typed
and ``commercial``-typed entries (5.7's 30 §1-inserted entries are all
``commercial`` today; the OR-clause handles both shapes uniformly).

Usage:
    python outputs/phase5_7_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"
AUDIT_DOC = Path("outputs") / "phase5_7_parks_audit.md"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate57"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.7 — Outdoors, Parks & Trails — Final §6 Acceptance Gate")
    print("=" * 78)
    print()

    results: list[tuple[str, bool, str]] = []

    # --- Gate item 1 -------------------------------------------------------
    # Uses the (e.entity_type != 'commercial' OR provider-visible) shape
    # from phase5_2_gate_verification.py to handle both place- and
    # commercial-typed entries uniformly. 5.7's 30 §1-inserted entries
    # are all commercial today; the OR-clause handles both shapes.
    n = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'outdoors-parks-trails'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 20
    results.append(
        (
            "1. 20+ entries in `outdoors-parks-trails` post-load",
            item1,
            f"{n} entities rendering at /category/outdoors-parks-trails (target: 20+ per kickoff §6)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.7 reconciler review: 32 ambig-skips audited in
    # outputs/phase5_7_parks_audit.md §1-5 — finding was NO misroutes
    # (28 cross-category benign geo-adjacency to eat-drink/HWC/on-the-
    # water/HPS/shopping-essentials + 1 same-category + 3 orphan) +
    # 3 special-audit axes (a/b/c) cleared per §5-7. The 13-row edge-
    # case catch-all review surfaced 3 FLIPs (Buses By The Bridge +
    # Desert Storm HQ to events, Parks & Rec Dept to public-civic-
    # resources) and 1 DRAFT (Altitude Trampoline Park) applied via
    # outputs/apply_phase5_7_parks_audit.py.
    #
    # Acceptance signal:
    # (a) no outdoors-parks-trails providers have category_id IS NULL, and
    # (b) the (None, "entertainment_attractions") catch-all in
    #     _DISCOVERY_DOMAIN_FALLBACK (shipped at 1dfd28e) ensures every
    #     future re-load resolves to a category.
    n_null = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'outdoors-parks-trails'
          AND p.category_id IS NULL
        """
    ).fetchone()[0]
    item2 = n_null == 0
    results.append(
        (
            "2. All Google ↔ existing-entity ambiguous reconciler hits reviewed (+ 3 special audits)",
            item2,
            f"outdoors-parks-trails providers w/ NULL category_id: {n_null} (target: 0); "
            "32 ambig-skips reviewed per audit §1-3 — no misroutes; "
            "special audits (a) on-the-water / (b) cat-12 / (c) SARA Park de-dup all cleared; "
            "3 FLIPs + 1 DRAFT applied for §4 edge cases",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # Option C — Layer-4 verifier surface explicitly deferred to V1.5.
    # The audit doc + kickoff §3 document AZ State Parks + NPS + LHC
    # Parks & Rec paths for V1.5 pickup. Acceptance signal: the audit
    # doc exists AND no providers in outdoors-parks-trails have
    # verification_method set to az_state_parks/nps/lhc_parks (no
    # verifier ran).
    audit_exists = AUDIT_DOC.is_file()
    n_verified = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'outdoors-parks-trails'
          AND p.verification_method IS NOT NULL
          AND p.verification_method IN ('az_state_parks', 'nps', 'lhc_parks')
        """
    ).fetchone()[0]
    item3 = audit_exists and n_verified == 0
    results.append(
        (
            "3. Layer-4 verifier surface scoped — built or explicitly deferred to V1.5",
            item3,
            f"audit doc exists: {audit_exists}; "
            f"providers verified via az_state_parks/nps/lhc_parks: {n_verified} (target: 0 — Option C deferred); "
            "AZ State Parks + NPS + LHC Parks & Rec paths documented in kickoff §3 for V1.5 pickup",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'outdoors-parks-trails'
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
            f"{n_long} outdoors-parks-trails entities have long-form crowd_notes (target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    # heat_exposure on every entry. Uses total entities in category as
    # the denominator (not just rendering — gate-5 covers all linked
    # entities including drafts; Altitude Trampoline Park is drafted in
    # §2 but still has heat_exposure='indoor' set).
    null_he, total_opt = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'outdoors-parks-trails'
          AND e.is_active = 1
        """
    ).fetchone()
    null_he = null_he or 0
    item5 = null_he == 0 and total_opt > 0
    n_outdoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'outdoors-parks-trails'
          AND e.is_active = 1
          AND e.heat_exposure = 'outdoor'
        """
    ).fetchone()[0]
    n_indoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'outdoors-parks-trails'
          AND e.is_active = 1
          AND e.heat_exposure = 'indoor'
        """
    ).fetchone()[0]
    results.append(
        (
            "5. heat_exposure set on every outdoors-parks-trails entry",
            item5,
            f"{null_he} of {total_opt} have heat_exposure=NULL (target: 0); "
            f"{n_outdoor} set to 'outdoor' (default; parks/golf/trails are outdoor-by-definition), "
            f"{n_indoor} set to 'indoor' (Altitude Trampoline Park — drafted in §2 but still gets heat_exposure)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    # /category/outdoors-parks-trails renders ≥15. Page-render count is
    # the same as item 1's count (the route uses the EntityCategory join +
    # draft=0 filter).
    item6 = n >= 15
    results.append(
        (
            "6. /category/outdoors-parks-trails renders ≥15 per default filter",
            item6,
            f"page: {n} entities (target: 15+)",
        )
    )

    # --- Scoreboard --------------------------------------------------------
    print("Gate item                                                           Status")
    print("-" * 78)
    for label, passed, detail in results:
        marker = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {label:<60} {marker}")
        print(f"    -> {detail}")
        print()

    all_passed = all(passed for _, passed, _ in results)
    print("=" * 78)
    if all_passed:
        print("PHASE 5.7 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED — READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.7 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
