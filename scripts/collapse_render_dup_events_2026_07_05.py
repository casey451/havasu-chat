"""3D Op 1 — physically collapse the render-time display-duplicate events.

The render dedup (``app.events.dedup.dedup_cross_source_occurrences``, the 3B/3.1
logic) HIDES cross-source twins at display time and shows one survivor that
ABSORBS the twin's flyer / longest description / real time / more-specific
location — but read-only (``set_committed_value``), so the duplicate rows and the
un-absorbed survivor stay in the DB. Admin/API surfaces that don't run the render
dedup still see the twins and a survivor missing the absorbed fields.

This op makes the DB match the deduped display: it reconstructs the SAME
survivor→loser clusters the render dedup produces, then for each cluster
  * PERSISTS the absorbed fields onto the survivor (real writes, mirroring
    ``_absorb_display_fields`` + the §3.1 location absorb), and
  * flips each loser to ``status="duplicate"`` (the convention
    ``dedupe_events_cross_source.py`` already uses) and folds its provenance into
    the survivor's ``source`` via ``combine_sources``.

Safety: a self-check asserts the reconstructed drop set EXACTLY matches the render
oracle's drop set before any write. DRY-RUN by default; ``--apply`` writes and
emits a full undo CSV (every survivor field change + every loser status flip).

    .venv\\Scripts\\python.exe -m scripts.collapse_render_dup_events_2026_07_05            # dry-run
    .venv\\Scripts\\python.exe -m scripts.collapse_render_dup_events_2026_07_05 --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date

from sqlalchemy import select

from app.contrib.event_reconciler import combine_sources
from app.db.database import SessionLocal
from app.db.models import Event
from app.events.dedup import (
    _cross_source_session_clusters,
    _group_clusters,
    _render_title_key,
    _source_priority,
    _start_is_tbd_for_dedup,
    dedup_cross_source_occurrences,
    is_bare_venue,
    location_has_street_address,
)

_UNDO_CSV = "collapse_render_dup_events_undo_2026-07-05.csv"


def _plan_absorb(survivor: Event, losers: list[Event]) -> list[tuple[str, object, object]]:
    """Return [(field, old, new)] the survivor should absorb — no mutation here."""
    changes: list[tuple[str, object, object]] = []

    if not (getattr(survivor, "image_url", None) or "").strip():
        for lo in losers:
            if (getattr(lo, "image_url", None) or "").strip():
                changes.append(("image_url", survivor.image_url, lo.image_url))
                break

    if _start_is_tbd_for_dedup(survivor.start_time, survivor.end_time):
        for lo in losers:
            if not _start_is_tbd_for_dedup(lo.start_time, lo.end_time):
                changes.append(("start_time", survivor.start_time, lo.start_time))
                changes.append(("end_time", survivor.end_time, lo.end_time))
                break

    if is_bare_venue(survivor.location_name):
        for lo in losers:
            if location_has_street_address(lo.location_name):
                changes.append(("location_name", survivor.location_name, lo.location_name))
                if lo.location_normalized:
                    changes.append(
                        ("location_normalized", survivor.location_normalized, lo.location_normalized)
                    )
                break

    current = (survivor.description or "").strip()
    authoritative = bool(getattr(survivor, "operator_override", False)) or _source_priority(
        survivor.source
    ) == 0
    if not (authoritative and current):
        best, best_len = survivor.description or "", len(current)
        for lo in losers:
            d = lo.description or ""
            if len(d.strip()) > best_len:
                best, best_len = d, len(d.strip())
        if best != (survivor.description or ""):
            changes.append(("description", survivor.description, best))

    return changes


def _clusters(occ: list[tuple[Event, date]]) -> list[tuple[int, list[int]]]:
    """Reconstruct the render dedup's (survivor_idx, [loser_idx]) clusters."""
    groups: dict[tuple[str, date], list[tuple[int, Event]]] = {}
    for idx, (ev, occ_date) in enumerate(occ):
        key = _render_title_key(ev)
        if key:
            groups.setdefault((key, occ_date), []).append((idx, ev))
    out: list[tuple[int, list[int]]] = []
    dropped: set[int] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        for survivor, losers in _group_clusters(members):
            if losers:
                out.append((survivor, losers))
                dropped.update(losers)
    for survivor, losers in _cross_source_session_clusters(occ, dropped):
        if losers:
            out.append((survivor, losers))
            dropped.update(losers)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collapse render-duplicate events.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        live = list(db.scalars(select(Event).where(Event.status == "live")).all())
        occ = [(e, e.date) for e in live]
        clusters = _clusters(occ)

        # Self-check: our reconstructed drop COUNT must equal the render oracle's.
        # Run the oracle on a SEPARATE session — dedup_cross_source_occurrences
        # mutates survivor objects in memory (set_committed_value), which would
        # otherwise pollute the working ``occ`` and make _plan_absorb see the
        # already-absorbed values and plan nothing.
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
                [("source", survivor.source, combined)] if combined != (survivor.source or "") else []
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

        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["kind", "id", "field", "old_value"])
            w.writerows(undo_rows)
        db.commit()
        print(
            f"APPLIED: deactivated {len(our_drops)} losers, {n_field_changes} survivor field "
            f"changes. Undo CSV: {_UNDO_CSV}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
