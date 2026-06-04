"""Shared dry-run reporting + apply-guard for source-expansion scrapers.

Every new scraper built under the source-expansion effort is **inert**: it
fetches and parses upstream data and reports what it *would* do, but performs no
database writes and is wired into no orchestrator. The persistence/orchestration
wiring is the per-source go/no-go integration step Casey greenlights later, after
reviewing the dry-run output.

This module gives all those CLI drivers one consistent contract so the dry-run
output Casey reviews looks the same across sources:

* :func:`print_dry_run_report` prints the standard contract — items fetched,
  would-insert / would-update / would-skip counts, and 3 sample records.
* :func:`apply_guard` is what ``--apply`` calls: it prints a prominent warning
  that live ingestion is intentionally not wired in this build-only branch and
  exits non-zero, so nobody (including an automated run) can accidentally write
  to prod from these modules before integration is approved.

``classify`` lets a driver that has a real read-only reconciliation path (events
against the events table, providers against the reconciler) produce meaningful
insert/update/skip counts. Sources with no store yet pass no classifier and
everything counts as a would-insert.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

# Decision labels a classifier may return.
INSERT = "insert"
UPDATE = "update"
SKIP = "skip"


@dataclass(frozen=True)
class DryRunCounts:
    fetched: int
    would_insert: int
    would_update: int
    would_skip: int


def summarize(
    records: Sequence[Any],
    *,
    classify: Callable[[Any], str] | None = None,
) -> DryRunCounts:
    """Bucket records into insert/update/skip. Default (no classifier): all insert."""
    insert = update = skip = 0
    for rec in records:
        decision = classify(rec) if classify is not None else INSERT
        if decision == UPDATE:
            update += 1
        elif decision == SKIP:
            skip += 1
        else:
            insert += 1
    return DryRunCounts(
        fetched=len(records),
        would_insert=insert,
        would_update=update,
        would_skip=skip,
    )


def _default_sample(rec: Any) -> dict[str, Any]:
    if hasattr(rec, "__dict__"):
        return {k: v for k, v in vars(rec).items() if not k.startswith("_")}
    if isinstance(rec, dict):
        return rec
    return {"value": repr(rec)}


def print_dry_run_report(
    name: str,
    records: Sequence[Any],
    *,
    classify: Callable[[Any], str] | None = None,
    sample_fn: Callable[[Any], dict[str, Any]] | None = None,
    sample_count: int = 3,
    notes: Sequence[str] = (),
) -> DryRunCounts:
    """Print the standard dry-run contract and return the counts.

    Output is deliberately plain text + JSON samples so it is easy to paste into
    a PR for review.
    """
    counts = summarize(records, classify=classify)
    sample_fn = sample_fn or _default_sample

    print(f"=== {name} — DRY RUN (no writes) ===")
    print(f"fetched:        {counts.fetched}")
    print(f"would-insert:   {counts.would_insert}")
    print(f"would-update:   {counts.would_update}")
    print(f"would-skip:     {counts.would_skip}")
    for line in notes:
        print(f"note: {line}")
    print(f"--- {min(sample_count, len(records))} sample record(s) ---")
    for rec in list(records)[:sample_count]:
        try:
            print(json.dumps(sample_fn(rec), default=str, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            print(repr(rec))
    if not records:
        print("(no records fetched)")
    return counts


def apply_guard(name: str) -> NoReturn:
    """``--apply`` entry point for a build-only scraper: warn loudly and exit.

    Live ingestion + orchestrator registration is the integration step gated on
    Casey's per-source go/no-go. These modules intentionally ship inert, so
    ``--apply`` never writes to the database.
    """
    print(f"!!! {name} --apply is NOT wired in this build-only branch. !!!")
    print(
        "Live ingestion and orchestrator registration are the integration step, "
        "gated on Casey's per-source go/no-go review of the dry-run output. "
        "No database writes were performed. Re-run with --dry-run."
    )
    raise SystemExit(2)
