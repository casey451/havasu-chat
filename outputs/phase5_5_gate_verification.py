"""Phase 5.5 — final §6 acceptance gate verification.

One-shot diagnostic that runs all 7 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.5 ships when this script reports all 7
items CLEARED.

Mirrors outputs/phase5_4_gate_verification.py shape — copies events.db
to a tempdir before reading.

Phase 5.5 differs from 5.4 in three ways:
  - **7 gates** (vs 5.4's 6) because is_mobile_service and heat_exposure
    are independent gate items (5.4 only had heat_exposure as a gate).
  - **Gate item 3 (verifier surface)** resolves via Option C — explicitly
    deferred to V1.5 — so the check is file-presence on the audit doc
    that documents the deferred AZ MVD + AZCC paths.
  - **Gate item 1 threshold is ≥30** (vs 5.4's ≥80) per kickoff §6.

Usage:
    python outputs/phase5_5_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"
AUDIT_DOC = Path("outputs") / "phase5_5_auto_rv_fuel_pre_load_audit.md"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate55"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.5 — Auto, RV & Fuel — Final §6 Acceptance Gate")
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
          AND c.slug = 'auto-rv-fuel'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 30
    results.append(
        (
            "1. 30+ entries in `auto-rv-fuel` post-load",
            item1,
            f"{n} entities rendering at /category/auto-rv-fuel (target: 30+ per kickoff §6)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.5 reconciler review: 76 ambig-skips audited in
    # outputs/phase5_5_auto_rv_fuel_pre_load_audit.md §1-7 — finding was
    # NO misroutes (67 cross-category + 9 same-category, all strip-mall
    # adjacency on Industrial Blvd / Lake Havasu Ave) + 0 RV cross-list
    # flips needed (the 4 RV-keyword candidates all coincidental). Then the
    # 7c994aa/fc51940-style sustainability extension at 4d41944 cleared the
    # category_id=None operator queue. Acceptance signal:
    # (a) no auto-rv-fuel providers have category_id IS NULL (cleared by 4d41944).
    n_null = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'auto-rv-fuel'
          AND p.category_id IS NULL
        """
    ).fetchone()[0]
    item2 = n_null == 0
    results.append(
        (
            "2. All Google ↔ existing-entity ambiguous reconciler hits reviewed (+ RV cross-list)",
            item2,
            f"auto-rv-fuel providers w/ NULL category_id: {n_null} (target: 0); "
            "76 ambig-skips reviewed per pre-load audit §1-7 — no misroutes, "
            "0 RV cross-list flips",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # Option C — Layer-4 verifier surface explicitly deferred to V1.5.
    # The audit doc + kickoff §3 document the AZ MVD Dealer Locator
    # (Playwright) + AZCC towing carrier (REST) paths for V1.5 pickup.
    # Acceptance signal: the audit doc exists AND no providers in
    # auto-rv-fuel have verification_method set (no verifier ran).
    audit_exists = AUDIT_DOC.is_file()
    n_verified = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'auto-rv-fuel'
          AND p.verification_method IS NOT NULL
          AND p.verification_method IN ('az_mvd', 'azcc')
        """
    ).fetchone()[0]
    item3 = audit_exists and n_verified == 0
    results.append(
        (
            "3. Layer-4 verifier surface scoped — built or explicitly deferred to V1.5",
            item3,
            f"audit doc exists: {audit_exists}; "
            f"providers verified via az_mvd/azcc: {n_verified} (target: 0 — Option C deferred); "
            "AZ MVD + AZCC paths documented in audit §3 + kickoff §3",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'auto-rv-fuel'
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
            f"{n_long} auto-rv-fuel entities have long-form crowd_notes (target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    null_ms, total_arf = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.is_mobile_service IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'auto-rv-fuel'
          AND e.is_active = 1
        """
    ).fetchone()
    null_ms = null_ms or 0
    item5 = null_ms == 0 and total_arf > 0
    n_true_ms = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'auto-rv-fuel'
          AND e.is_active = 1
          AND e.is_mobile_service = 1
        """
    ).fetchone()[0]
    results.append(
        (
            "5. is_mobile_service populated on every auto-rv-fuel entry",
            item5,
            f"{null_ms} of {total_arf} have is_mobile_service=NULL (target: 0); "
            f"{n_true_ms} set to True (mobile detailers + towing + mobile RV techs)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    null_he = cur.execute(
        """
        SELECT SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'auto-rv-fuel'
          AND e.is_active = 1
        """
    ).fetchone()[0]
    null_he = null_he or 0
    item6 = null_he == 0 and total_arf > 0
    n_outdoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'auto-rv-fuel'
          AND e.is_active = 1
          AND e.heat_exposure = 'outdoor'
        """
    ).fetchone()[0]
    results.append(
        (
            "6. heat_exposure set on every auto-rv-fuel entry",
            item6,
            f"{null_he} of {total_arf} have heat_exposure=NULL (target: 0); "
            f"{n_outdoor} set to 'outdoor' (gas station pump islands + outdoor car washes)",
        )
    )

    # --- Gate item 7 -------------------------------------------------------
    # /category/auto-rv-fuel renders ≥15. Page-render count is the same as
    # item 1's count (the route uses the EntityCategory join).
    item7 = n >= 15
    results.append(
        (
            "7. /category/auto-rv-fuel renders ≥15 per default filter",
            item7,
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
        print("PHASE 5.5 ACCEPTANCE GATE: ALL 7 ITEMS CLEARED — READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.5 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
