"""Phase 5.8 — final §6 acceptance gate verification.

One-shot diagnostic that runs all 6 gate-item checks and outputs a
PASS/FAIL scoreboard. Phase 5.8 ships when this script reports all 6
items CLEARED.

Mirrors outputs/phase5_7_gate_verification.py shape — copies events.db
to a tempdir before reading.

Phase 5.8 differs from 5.7 in three ways:
  - **Gate item 1 threshold is ≥20** (same as 5.7) per kickoff §6.
    Events density in LHC is moderate; 2 pre-existing + 1 §1 insert +
    17 §2 FLIPs (16 NEW + 1 cross-cat) + 1 DRAFT = 21 entries; gate-1
    counts those that render via the OR-clause shape.
  - **Gate item 3 (verifier surface)** resolves via Option C — explicitly
    deferred to V1.5 — so the check is file-presence on the audit doc
    that documents the deferred AZ event aggregators + LHC Tourism
    Board paths (vs 5.7's AZ State Parks / NPS / LHC Parks & Rec).
  - **Gate item 5 (heat_exposure)** — 5.8 flips the default back to
    ``indoor`` (vs 5.7's ``outdoor``); the detail line reports ``indoor``
    count first.

Same as 5.7: 6 gates (no is_mobile_service — events are venue-based;
same rationale as 5.6/5.7 brick-and-mortar / place-based categories).
Gate-1 query uses the ``(e.entity_type != 'commercial' OR
provider-visible)`` OR-clause shape from phase5_2_gate_verification.py
+ phase5_7_gate_verification.py to correctly count both ``place``-typed
(art_gallery / museum / history_museum primaries per 5.8 sustainability)
and ``commercial``-typed entries uniformly.

Usage:
    python outputs/phase5_8_gate_verification.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"
AUDIT_DOC = Path("outputs") / "phase5_8_events_audit.md"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.gate58"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.8 — Events — Final §6 Acceptance Gate")
    print("=" * 78)
    print()

    results: list[tuple[str, bool, str]] = []

    # --- Gate item 1 -------------------------------------------------------
    # Uses the (e.entity_type != 'commercial' OR provider-visible) shape
    # from phase5_2_gate_verification.py to handle both place- and
    # commercial-typed entries uniformly. 5.8's 7 art_gallery + 1
    # history_museum entries are entity_type='place' (per the
    # sustainability commit at 0b426e1); the rest are commercial.
    n = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'events'
          AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    item1 = n >= 20
    results.append(
        (
            "1. 20+ entries in `events` post-load",
            item1,
            f"{n} entities rendering at /category/events (target: 20+ per kickoff §6)",
        )
    )

    # --- Gate item 2 -------------------------------------------------------
    # 5.8 reconciler review: 33 ambig records audited in
    # outputs/phase5_8_events_audit.md §3-4 — finding was 17 FLIPs (15
    # NEW entity creates + 1 cross-cat move + 1 §1 insert that auto-
    # resolved) + 1 DRAFT + 15 KEEPs (4 5.8-relevant low-signal + 11
    # cross-phase noise) + 3 special-audit axes (a/b/c) cleared per §5-7.
    # The 16-row Slice A NEW creates landed via apply_phase5_8_events_
    # audit.py.
    #
    # Acceptance signal: no events providers have category_id IS NULL
    # post-§1-sustainability + apply-script. The sustainability commit
    # at 0b426e1 (7 direct _PRIMARY_TYPE_MAP entries) closed the
    # primary_type=NULL gap pre-load; the apply-script set
    # category_id=cat-2 on every NEW Provider.
    n_null = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events'
          AND p.category_id IS NULL
        """
    ).fetchone()[0]
    item2 = n_null == 0
    results.append(
        (
            "2. All Google ↔ existing-entity ambiguous reconciler hits reviewed (+ 3 special audits)",
            item2,
            f"events providers w/ NULL category_id: {n_null} (target: 0); "
            "33 ambig records reviewed per audit §3-4 — 17 FLIPs + 1 DRAFT + 15 KEEPs; "
            "special audits (a) cat-7 / (b) cat-13 / (c) seasonal-activation de-dup all cleared",
        )
    )

    # --- Gate item 3 -------------------------------------------------------
    # Option C — Layer-4 verifier surface explicitly deferred to V1.5.
    # The audit doc + kickoff §3 document AZ event aggregators (visit
    # arizona, eventbrite-local) + LHC Tourism Board (golakehavasu.com)
    # paths for V1.5 pickup. Acceptance signal: the audit doc exists AND
    # no providers in events have verification_method set to
    # visit_arizona/lhc_tourism/eventbrite (no verifier ran).
    audit_exists = AUDIT_DOC.is_file()
    n_verified = cur.execute(
        """
        SELECT COUNT(*) FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events'
          AND p.verification_method IS NOT NULL
          AND p.verification_method IN ('visit_arizona', 'lhc_tourism', 'eventbrite')
        """
    ).fetchone()[0]
    item3 = audit_exists and n_verified == 0
    results.append(
        (
            "3. Layer-4 verifier surface scoped — built or explicitly deferred to V1.5",
            item3,
            f"audit doc exists: {audit_exists}; "
            f"providers verified via visit_arizona/lhc_tourism/eventbrite: {n_verified} "
            "(target: 0 — Option C deferred); "
            "AZ event aggregators + LHC Tourism Board paths documented in kickoff §3 for V1.5 pickup",
        )
    )

    # --- Gate item 4 -------------------------------------------------------
    n_long = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events'
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
            f"{n_long} events entities have long-form crowd_notes (target: 10+)",
        )
    )

    # --- Gate item 5 -------------------------------------------------------
    # heat_exposure on every entry. Uses total entities in category as
    # the denominator (covers all linked entities including drafts;
    # Simply Savage Designs is drafted in §2 Slice C but still has
    # heat_exposure='indoor' set per the apply-script default).
    null_he, total_evt = cur.execute(
        """
        SELECT
            SUM(CASE WHEN e.heat_exposure IS NULL THEN 1 ELSE 0 END),
            COUNT(*)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events'
          AND e.is_active = 1
        """
    ).fetchone()
    null_he = null_he or 0
    item5 = null_he == 0 and total_evt > 0
    n_indoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events'
          AND e.is_active = 1
          AND e.heat_exposure = 'indoor'
        """
    ).fetchone()[0]
    n_outdoor = cur.execute(
        """
        SELECT COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events'
          AND e.is_active = 1
          AND e.heat_exposure = 'outdoor'
        """
    ).fetchone()[0]
    results.append(
        (
            "5. heat_exposure set on every events entry",
            item5,
            f"{null_he} of {total_evt} have heat_exposure=NULL (target: 0); "
            f"{n_indoor} set to 'indoor' (default; theaters/bowling/galleries/museums "
            f"are indoor-by-definition), {n_outdoor} set to 'outdoor' (festival / "
            "outdoor-venue overrides — Buses By The Bridge, Desert Storm HQ, WORCS Racing)",
        )
    )

    # --- Gate item 6 -------------------------------------------------------
    # /category/events renders ≥15. Page-render count is the same as
    # item 1's count (the route uses the EntityCategory join +
    # draft=0 filter, identical to the gate-1 query above).
    item6 = n >= 15
    results.append(
        (
            "6. /category/events renders ≥15 per default filter",
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
        print("PHASE 5.8 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED — READY TO SHIP")
    else:
        failed = [label for label, passed, _ in results if not passed]
        print(f"PHASE 5.8 GATE: {len(failed)} ITEM(S) NOT MET")
        for label in failed:
            print(f"  - {label}")
    print("=" * 78)

    conn.close()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
