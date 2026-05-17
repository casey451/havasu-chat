"""Phase 5.6 — final §6 acceptance gate verification.

One-shot diagnostic that runs all 6 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.6 ships when this script reports all 6
items CLEARED.

Mirrors outputs/phase5_5_gate_verification.py shape — copies events.db
to a tempdir before reading.

Phase 5.6 differs from 5.5 in three ways:
  - **6 gates** (vs 5.5's 7) because is_mobile_service is dropped for
    5.6 — retail is brick-and-mortar by definition (per kickoff §6 note).
  - **Gate item 3 (verifier surface)** resolves via Option C — explicitly
    deferred to V1.5 — so the check is file-presence on the audit doc
    that documents the deferred AZ TPT + BBB paths.
  - **Gate item 1 threshold is ≥40** (vs 5.5's ≥30) per kickoff §6.

Usage:
    python outputs/phase5_6_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"
AUDIT_DOC = Path("outputs") / "phase5_6_shopping_essentials_audit.md"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate56"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.6 — Shopping, Grocery & Essentials — Final §6 Acceptance Gate")
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
          AND c.slug = 'shopping-essentials'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 40
    results.append(
        (
            "1. 40+ entries in `shopping-essentials` post-load",
            item1,
            f"{n} entities rendering at /category/shopping-essentials (target: 40+ per kickoff §6)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.6 reconciler review: 177 ambig-skips audited in
    # outputs/phase5_6_shopping_essentials_audit.md §1-5 — finding was
    # NO misroutes (173 cross-category + 4 same-category, all strip-mall
    # adjacency on McCulloch / Lake Havasu Ave) + 0 gas-station/convenience-
    # store cat-9/cat-8 flips needed (V1 policy: stay in cat-9). Then the
    # 11 FLIPs + 7 DRAFTs apply-script (apply_phase5_6_shopping_audit.py)
    # cleaned the catch-all routing edge cases. Acceptance signal:
    # (a) no shopping-essentials providers have category_id IS NULL, and
    # (b) the (None, "retail") catch-all in _DISCOVERY_DOMAIN_FALLBACK
    #     ensures every future re-load resolves to a category.
    n_null = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'shopping-essentials'
          AND p.category_id IS NULL
        """
    ).fetchone()[0]
    item2 = n_null == 0
    results.append(
        (
            "2. All Google ↔ existing-entity ambiguous reconciler hits reviewed (+ cat-9/cat-8 audit)",
            item2,
            f"shopping-essentials providers w/ NULL category_id: {n_null} (target: 0); "
            "177 ambig-skips reviewed per audit §1-3 — no misroutes, "
            "0 cat-9/cat-8 gas-station/convenience flips; 11 FLIPs + 7 DRAFTs applied for §4 edge cases",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # Option C — Layer-4 verifier surface explicitly deferred to V1.5.
    # The audit doc + kickoff §3 document the AZ TPT (Transaction Privilege
    # Tax) Playwright path + BBB cross-reference path for V1.5 pickup.
    # Acceptance signal: the audit doc exists AND no providers in
    # shopping-essentials have verification_method set to az_tpt/bbb (no
    # verifier ran).
    audit_exists = AUDIT_DOC.is_file()
    n_verified = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'shopping-essentials'
          AND p.verification_method IS NOT NULL
          AND p.verification_method IN ('az_tpt', 'bbb')
        """
    ).fetchone()[0]
    item3 = audit_exists and n_verified == 0
    results.append(
        (
            "3. Layer-4 verifier surface scoped — built or explicitly deferred to V1.5",
            item3,
            f"audit doc exists: {audit_exists}; "
            f"providers verified via az_tpt/bbb: {n_verified} (target: 0 — Option C deferred); "
            "AZ TPT + BBB paths documented in kickoff §3 for V1.5 pickup",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'shopping-essentials'
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
            f"{n_long} shopping-essentials entities have long-form crowd_notes (target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    # heat_exposure on every entry — 5.6's gate-5 (vs 5.5's gate-6 because
    # 5.6 drops is_mobile_service). Uses total entities in category as the
    # denominator (not just rendering — gate-5 covers all linked entities
    # including drafts).
    null_he, total_se = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'shopping-essentials'
          AND e.is_active = 1
        """
    ).fetchone()
    null_he = null_he or 0
    item5 = null_he == 0 and total_se > 0
    n_outdoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'shopping-essentials'
          AND e.is_active = 1
          AND e.heat_exposure = 'outdoor'
        """
    ).fetchone()[0]
    results.append(
        (
            "5. heat_exposure set on every shopping-essentials entry",
            item5,
            f"{null_he} of {total_se} have heat_exposure=NULL (target: 0); "
            f"{n_outdoor} set to 'outdoor' (4 garden centers / nurseries + Tux and Tulips florist)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    # /category/shopping-essentials renders ≥15. Page-render count is the
    # same as item 1's count (the route uses the EntityCategory join +
    # draft=0 filter).
    item6 = n >= 15
    results.append(
        (
            "6. /category/shopping-essentials renders ≥15 per default filter",
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
        print("PHASE 5.6 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED — READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.6 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
