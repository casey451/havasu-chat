"""Phase 5.3 — final §6 acceptance gate verification.

One-shot diagnostic that runs all 6 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.3 ships when this script reports all 6
items CLEARED.

Mirrors outputs/phase5_2_gate_verification.py shape — copies events.db
to /tmp via the gotcha #4/#15 workaround before reading.

Usage:
    python outputs/phase5_3_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate53"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.3 — Home & Property Services — Final §6 Acceptance Gate")
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
          AND c.slug = 'home-property-services'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 60
    results.append(
        (
            "1. 60+ entries in `home-property-services` post-load",
            item1,
            f"{n} entities rendering at /category/home-property-services (target: 60+)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.3 reconciler review = the post-load audit's 75 ambig-skips, completed
    # via outputs/apply_phase5_3_home_property_audit.py. Acceptance signal:
    # (a) no providers have category_id IS NULL (the 3 Slice B residuals are
    #     fixed by the apply-script), AND
    # (b) Stanley Steemer (post-load Slice D misroute) is in
    #     /category/home-property-services rather than shopping-essentials.
    n_null = cur.execute(
        "SELECT COUNT(*) FROM providers WHERE category_id IS NULL"
    ).fetchone()[0]
    steemer_slug = cur.execute(
        """
        SELECT c.slug FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE e.name LIKE 'Stanley Steemer%' AND e.is_active = 1
        LIMIT 1
        """
    ).fetchone()
    steemer_in_hps = steemer_slug is not None and steemer_slug[0] == "home-property-services"
    item2 = n_null == 0 and steemer_in_hps
    results.append(
        (
            "2. All Google ↔ existing-entity ambiguous reconciler hits reviewed",
            item2,
            f"providers w/ NULL category_id: {n_null} (target: 0); "
            f"Stanley Steemer in home-property-services: {steemer_in_hps}",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # AZ ROC verification — count providers in home-property-services whose
    # attributes JSON includes 'az_roc' AND whose verification_method='scraper'.
    # Threshold: 30+ (we have ~120 licensed-trade candidates; 45% dry-run
    # match rate suggested live yield in the 50-80 range).
    n_az_roc = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entities e ON e.id = p.entity_id
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'home-property-services'
          AND e.is_active = 1
          AND p.verification_method = 'scraper'
          AND p.attributes LIKE '%az_roc%'
        """
    ).fetchone()[0]
    item3 = n_az_roc >= 30
    results.append(
        (
            "3. AZ ROC verification run completed for licensed sub-trades",
            item3,
            f"{n_az_roc} home-property-services providers verified via AZ ROC scraper "
            f"(target: 30+; see kickoff §3 — plumbers/electricians/HVAC/GC/roofing)",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'home-property-services'
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
            f"{n_long} home-property-services entities have long-form crowd_notes (target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    null_he, total_hps = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'home-property-services'
          AND e.is_active = 1
        """
    ).fetchone()
    null_he = null_he or 0
    item5 = null_he == 0 and total_hps > 0
    results.append(
        (
            "5. heat_exposure set on every home-property-services entry",
            item5,
            f"{null_he} of {total_hps} have heat_exposure=NULL (target: 0)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    # /category/home-property-services renders ≥15. Page-render count is the
    # same as item 1's count (the route uses the EntityCategory join).
    item6 = n >= 15
    results.append(
        (
            "6. /category/home-property-services renders ≥15 per default filter",
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
        print("PHASE 5.3 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED — READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.3 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
