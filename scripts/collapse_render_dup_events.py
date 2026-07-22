"""Collapse render-time display-duplicate events — generic, re-runnable op.

Generalizes ``scripts/collapse_render_dup_events_2026_07_05.py`` (its cluster
reconstruction + absorb planning are IMPORTED from there, so the two can never
drift) with one difference: the undo CSV is stamped per run instead of
hardcoded, so the op can be re-run as new twins accumulate. Occasion for the
generalization (2026-07-22): the all-day + 8 AM "Pickleball Open Play" pairs
(one per day on the rolling forward window) and the 3 AM "Troy's Alligator
Feed" AM/PM window-misparse twin, which the pre-dawn demotion fix in
``app/events/dedup.py`` now includes in the render oracle's drop set.

Same safety story as the dated op: the reconstructed drop set is asserted
against the render oracle before any write; DRY-RUN by default; ``--apply``
writes and emits the undo CSV (every survivor field change + every loser
status flip to ``status="duplicate"``).

    .venv\\Scripts\\python.exe -m scripts.collapse_render_dup_events            # dry-run
    .venv\\Scripts\\python.exe -m scripts.collapse_render_dup_events --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.event_reconciler import combine_sources  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.dedup import dedup_cross_source_occurrences  # noqa: E402
from scripts.collapse_render_dup_events_2026_07_05 import (  # noqa: E402
    _clusters,
    _plan_absorb,
)


def _undo_csv_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"collapse_render_dup_events_undo_{stamp}.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collapse render-duplicate events (generic re-runnable op)."
    )
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)
    undo_csv = _undo_csv_name()

    with SessionLocal() as db:
        live = list(db.scalars(select(Event).where(Event.status == "live")).all())
        occ = [(e, e.date) for e in live]
        clusters = _clusters(occ)

        # Self-check: our reconstructed drop COUNT must equal the render
        # oracle's (run on a SEPARATE session — the oracle grafts absorbed
        # values onto survivors in memory, which would otherwise pollute the
        # working ``occ`` and make _plan_absorb plan nothing).
        our_drops = {i for _s, losers in clusters for i in losers}
        with SessionLocal() as check_db:
            check_live = list(
                check_db.scalars(select(Event).where(Event.status == "live")).all()
            )
            check_occ = [(e, e.date) for e in check_live]
            oracle_drops_n = len(check_occ) - len(dedup_cross_source_occurrences(check_occ))
        if len(our_drops) != oracle_drops_n:
            print(
                f"ABORT: reconstructed drops ({len(our_drops)}) != oracle drops "
                f"({oracle_drops_n}) — refusing to write.",
                file=sys.stderr,
            )
            return 1

        print(f"live={len(live)}  clusters={len(clusters)}  losers_to_deactivate={len(our_drops)}")
        undo_rows: list[list[object]] = []
        n_field_changes = 0
        for survivor_idx, loser_idxs in clusters:
            survivor = occ[survivor_idx][0]
            losers = [occ[i][0] for i in loser_idxs]
            field_changes = _plan_absorb(survivor, losers)
            combined = survivor.source or ""
            for lo in losers:
                combined = combine_sources(combined, lo.source or "")
            src_change = (
                [("source", survivor.source, combined)]
                if combined != (survivor.source or "")
                else []
            )
            print(
                f"  survivor={str(survivor.id)[:8]} {survivor.date} '{(survivor.title or '')[:34]}' "
                f"<- {len(losers)} loser(s) {[str(lo.id)[:8] for lo in losers]}; "
                f"absorb={[c[0] for c in field_changes] + [c[0] for c in src_change]}"
            )

            if args.apply:
                for field, old, new in field_changes + src_change:
                    undo_rows.append(["survivor_field", survivor.id, field, old])
                    setattr(survivor, field, new)
                    n_field_changes += 1
                for lo in losers:
                    undo_rows.append(["loser_status", lo.id, "status", lo.status])
                    lo.status = "duplicate"

        if not args.apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
            return 0

        with open(undo_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["kind", "id", "field", "old_value"])
            w.writerows(undo_rows)
        db.commit()
        print(
            f"APPLIED: deactivated {len(our_drops)} losers, {n_field_changes} survivor field "
            f"changes. Undo CSV: {undo_csv}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
