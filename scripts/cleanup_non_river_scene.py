"""
Delete non–River-Scene catalog rows in one transaction (programs, seed providers,
admin/scraped data paths, field history, LLM mentions, operator backfill contribution).

  python scripts/cleanup_non_river_scene.py              # preview (default)
  python scripts/cleanup_non_river_scene.py --dry-run  # explicit preview
  python scripts/cleanup_non_river_scene.py --apply    # prompts for ``yes``, then deletes
  python scripts/cleanup_non_river_scene.py --apply --yes   # non-interactive apply

Preview mode issues **SELECT** queries only (no COMMIT of destructive work).

**Exit codes (``main`` / CLI):**

  **0** — success (dry-run or apply completed).

  **2** — argparse usage error (e.g. ``--dry-run`` and ``--apply`` together, or ``--yes`` without ``--apply``).

  **3** — pre-flight failed (``PreflightError``): RS counts below configured floor, or an RS
  contribution's ``created_event_id`` points at an admin-sourced event.

  **5** — apply aborted: user did not type exactly ``yes`` at the confirmation prompt
  (``ApplyAborted``). Not used when ``--yes`` is passed.

Environment (optional overrides for pre-flight floors, default prod inventory):

  CLEANUP_MIN_RS_CONTRIBUTIONS   default ``71``
  CLEANUP_MIN_RS_EVENTS          default ``71``
"""

from __future__ import annotations

import argparse
import builtins
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import (
    Contribution,
    Event,
    FieldHistory,
    LlmMentionedEntity,
    Program,
    Provider,
)

RS_SOURCE = "river_scene_import"
OPERATOR_BACKFILL = "operator_backfill"
ADMIN_EVENT_SOURCE = "admin"


@dataclass(frozen=True)
class CleanupCounts:
    llm_mentioned_entities: int
    field_history: int
    contributions_non_rs: int
    events_non_rs: int
    programs: int
    providers: int

    @property
    def total(self) -> int:
        return (
            self.llm_mentioned_entities
            + self.field_history
            + self.contributions_non_rs
            + self.events_non_rs
            + self.programs
            + self.providers
        )


def _min_rs_contributions() -> int:
    return int(os.environ.get("CLEANUP_MIN_RS_CONTRIBUTIONS", "71"))


def _min_rs_events() -> int:
    return int(os.environ.get("CLEANUP_MIN_RS_EVENTS", "71"))


def count_deletable_rows(db: Session) -> CleanupCounts:
    n_llm = int(db.scalar(select(func.count()).select_from(LlmMentionedEntity)) or 0)
    n_fh = int(db.scalar(select(func.count()).select_from(FieldHistory)) or 0)
    n_c = int(
        db.scalar(
            select(func.count()).select_from(Contribution).where(Contribution.source == OPERATOR_BACKFILL)
        )
        or 0
    )
    n_e = int(
        db.scalar(
            select(func.count()).select_from(Event).where(Event.source == ADMIN_EVENT_SOURCE)
        )
        or 0
    )
    n_p = int(db.scalar(select(func.count()).select_from(Program)) or 0)
    n_pr = int(db.scalar(select(func.count()).select_from(Provider)) or 0)
    return CleanupCounts(
        llm_mentioned_entities=n_llm,
        field_history=n_fh,
        contributions_non_rs=n_c,
        events_non_rs=n_e,
        programs=n_p,
        providers=n_pr,
    )


def run_preflight(db: Session, *, min_rs_contributions: int | None = None, min_rs_events: int | None = None) -> None:
    """Abort with ``PreflightError`` if RS inventory checks fail or illegal RS→admin links exist."""
    min_c = _min_rs_contributions() if min_rs_contributions is None else min_rs_contributions
    min_e = _min_rs_events() if min_rs_events is None else min_rs_events

    rs_c = int(
        db.scalar(select(func.count()).select_from(Contribution).where(Contribution.source == RS_SOURCE)) or 0
    )
    rs_e = int(db.scalar(select(func.count()).select_from(Event).where(Event.source == RS_SOURCE)) or 0)

    if rs_c < min_c:
        raise PreflightError(
            f"RS contributions count {rs_c} < expected minimum {min_c} — refusing cleanup (inventory drift)."
        )
    if rs_e < min_e:
        raise PreflightError(
            f"RS events count {rs_e} < expected minimum {min_e} — refusing cleanup (inventory drift)."
        )

    bad = int(
        db.scalar(
            select(func.count())
            .select_from(Contribution)
            .join(Event, Contribution.created_event_id == Event.id)
            .where(Contribution.source == RS_SOURCE, Event.source == ADMIN_EVENT_SOURCE)
        )
        or 0
    )
    if bad:
        raise PreflightError(
            f"Found {bad} RS contribution(s) with created_event_id pointing at admin-sourced events — refusing cleanup."
        )


class PreflightError(Exception):
    """Raised when RS safety checks fail before any destructive statement."""


class ApplyAborted(Exception):
    """User declined the interactive confirmation prompt."""


def _print_summary(mode: Literal["dry-run", "apply"], counts: CleanupCounts) -> None:
    print(f"Cleanup complete (mode: {mode})")
    print(f"  llm_mentioned_entities:    {counts.llm_mentioned_entities}")
    print(f"  field_history:             {counts.field_history}")
    print(f"  contributions (non-RS):   {counts.contributions_non_rs}")
    print(f"  events (non-RS):          {counts.events_non_rs}")
    print(f"  programs:                  {counts.programs}")
    print(f"  providers:                 {counts.providers}")
    print(f"  total:                     {counts.total}")


def _prompt_apply(counts: CleanupCounts, input_fn: Callable[[str], str] = input) -> bool:
    print("Proposed deletions (from current database):")
    print(f"  llm_mentioned_entities:    {counts.llm_mentioned_entities}")
    print(f"  field_history:             {counts.field_history}")
    print(f"  contributions (non-RS):   {counts.contributions_non_rs}")
    print(f"  events (non-RS):          {counts.events_non_rs}")
    print(f"  programs:                  {counts.programs}")
    print(f"  providers:                 {counts.providers}")
    print(f"  total:                     {counts.total}")
    print()
    answer = input_fn("Type 'yes' to apply these deletions (transactional, irreversible): ")
    return answer.strip() == "yes"


def _clear_fks_before_program_provider_delete(db: Session) -> None:
    """Detach surviving rows from programs/providers so DELETE does not violate FKs."""
    db.execute(update(Contribution).values(created_program_id=None).where(Contribution.created_program_id.is_not(None)))
    db.execute(update(Event).values(provider_id=None).where(Event.provider_id.is_not(None)))
    db.execute(
        update(Contribution).values(created_provider_id=None).where(Contribution.created_provider_id.is_not(None))
    )


def _execute_six_deletes(
    db: Session,
    *,
    expected: CleanupCounts,
    inject_failure_before: Literal[
        "llm_mentioned_entities",
        "field_history",
        "contributions",
        "events",
        "programs",
        "providers",
        "none",
    ] = "none",
) -> CleanupCounts:
    """Run FK clears plus six DELETEs in the current transaction; assert rowcounts match ``expected``."""
    if inject_failure_before == "llm_mentioned_entities":
        raise RuntimeError("injected DB failure")

    r1 = db.execute(delete(LlmMentionedEntity))
    n1 = r1.rowcount or 0
    if n1 != expected.llm_mentioned_entities:
        raise AssertionError(f"llm_mentioned_entities deleted {n1} != expected {expected.llm_mentioned_entities}")

    if inject_failure_before == "field_history":
        raise RuntimeError("injected DB failure")

    r2 = db.execute(delete(FieldHistory))
    n2 = r2.rowcount or 0
    if n2 != expected.field_history:
        raise AssertionError(f"field_history deleted {n2} != expected {expected.field_history}")

    if inject_failure_before == "contributions":
        raise RuntimeError("injected DB failure")

    r3 = db.execute(delete(Contribution).where(Contribution.source == OPERATOR_BACKFILL))
    n3 = r3.rowcount or 0
    if n3 != expected.contributions_non_rs:
        raise AssertionError(f"contributions deleted {n3} != expected {expected.contributions_non_rs}")

    if inject_failure_before == "events":
        raise RuntimeError("injected DB failure")

    r4 = db.execute(delete(Event).where(Event.source == ADMIN_EVENT_SOURCE))
    n4 = r4.rowcount or 0
    if n4 != expected.events_non_rs:
        raise AssertionError(f"events deleted {n4} != expected {expected.events_non_rs}")

    _clear_fks_before_program_provider_delete(db)

    if inject_failure_before == "programs":
        raise RuntimeError("injected DB failure")

    r5 = db.execute(delete(Program))
    n5 = r5.rowcount or 0
    if n5 != expected.programs:
        raise AssertionError(f"programs deleted {n5} != expected {expected.programs}")

    if inject_failure_before == "providers":
        raise RuntimeError("injected DB failure")

    r6 = db.execute(delete(Provider))
    n6 = r6.rowcount or 0
    if n6 != expected.providers:
        raise AssertionError(f"providers deleted {n6} != expected {expected.providers}")

    return CleanupCounts(
        llm_mentioned_entities=n1,
        field_history=n2,
        contributions_non_rs=n3,
        events_non_rs=n4,
        programs=n5,
        providers=n6,
    )


def run_cleanup(
    db: Session,
    *,
    apply: bool,
    assume_yes: bool = False,
    min_rs_contributions: int | None = None,
    min_rs_events: int | None = None,
    input_fn: Callable[[str], str] | None = None,
    inject_failure_before: Literal[
        "llm_mentioned_entities",
        "field_history",
        "contributions",
        "events",
        "programs",
        "providers",
        "none",
    ] = "none",
) -> CleanupCounts:
    """
    Preview (``apply=False``) or delete (``apply=True``) non-RS rows.

    When ``apply=True`` and ``assume_yes=False``, calls ``input_fn`` for confirmation unless
    ``inject_failure_before`` is used (tests).
    """
    run_preflight(db, min_rs_contributions=min_rs_contributions, min_rs_events=min_rs_events)
    expected = count_deletable_rows(db)

    if not apply:
        _print_summary("dry-run", expected)
        db.rollback()
        return expected

    _stdin: Callable[[str], str] = input_fn or builtins.input

    if not assume_yes and inject_failure_before == "none":
        if not _prompt_apply(expected, input_fn=_stdin):
            print("Aborted (confirmation was not exactly 'yes').", file=sys.stderr)
            db.rollback()
            raise ApplyAborted("confirmation was not exactly 'yes'")

    db.rollback()
    with db.begin():
        actual = _execute_six_deletes(db, expected=expected, inject_failure_before=inject_failure_before)

    _print_summary("apply", actual)
    return actual


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    epilog = """exit codes: 0 success | 2 argparse | 3 preflight (PreflightError) | 5 apply declined (ApplyAborted)"""
    p = argparse.ArgumentParser(description=__doc__, epilog=epilog)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview counts only (no writes). Same as default when --apply is omitted.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Run transactional DELETE after confirmation (or with --yes).",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="With --apply, skip the interactive confirmation prompt.",
    )
    ns = p.parse_args(argv)
    if ns.yes and not ns.apply:
        p.error("--yes requires --apply")
    return ns


def main(argv: list[str] | None = None) -> int:
    """Entry point. Optional ``argv`` replaces ``sys.argv`` (excluding program name), for tests."""
    args = _parse_args(argv)
    apply = bool(args.apply)

    with SessionLocal() as db:
        try:
            run_cleanup(db, apply=apply, assume_yes=bool(args.yes))
        except PreflightError as e:
            print(str(e), file=sys.stderr)
            return 3
        except ApplyAborted:
            return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
