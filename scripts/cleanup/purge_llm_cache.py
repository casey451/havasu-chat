"""One-shot cleanup: purge all LlmResponseCache rows.

Use this after any change that invalidates cached LLM responses:

* Feature flag flip (e.g. FEATURE_FLAG_CONFIDENCE_TIER on→off — Backlog #49).
* Prompt file changes (`prompts/system_prompt.txt`, `prompts/tier2_formatter.txt`).
* Schema changes that affect retrieval (e.g. Provider category remap).
* Production-bug fixes that change response shape (e.g. entity matcher #46/#47).

The cache is a 7-day TTL backing table (`DEFAULT_TTL_DAYS = 7` in
``app/chat/llm_cache.py``). Without an explicit purge, polluted entries
linger up to a week.

Usage:
    # See how many rows would be deleted, without writing
    python -m scripts.cleanup.purge_llm_cache --dry-run

    # Actually purge (requires DATABASE_URL env var pointing at production)
    python -m scripts.cleanup.purge_llm_cache --apply

    # Optional: filter to entries older than N days (e.g. expire-only cleanup)
    python -m scripts.cleanup.purge_llm_cache --apply --older-than-days 7

The ``--apply`` flag refuses to run unless ``DATABASE_URL`` is set explicitly
in the environment, as a guard against accidental production access from a
local dev shell. ``--dry-run`` works against any reachable DB (local SQLite
or production Postgres).

Logs every run with row counts to scripts/cleanup/logs/purge_llm_cache_<ts>.log.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import delete, func, select  # noqa: E402  -- requires _ROOT on sys.path

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import LlmResponseCache  # noqa: E402

_LOG_DIR = _ROOT / "scripts" / "cleanup" / "logs"


@dataclass(frozen=True)
class PurgeResult:
    matched: int
    deleted: int
    log_path: Path
    older_than_days: int | None


def _ensure_log_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def _new_log_path(mode: str) -> Path:
    _ensure_log_dir()
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _LOG_DIR / f"purge_llm_cache_{mode}_{ts}.log"


def _count_matching(db, older_than_days: int | None) -> int:
    stmt = select(func.count()).select_from(LlmResponseCache)
    if older_than_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        stmt = stmt.where(LlmResponseCache.created_at < cutoff)
    return int(db.scalar(stmt) or 0)


def _delete_matching(db, older_than_days: int | None) -> int:
    stmt = delete(LlmResponseCache)
    if older_than_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        stmt = stmt.where(LlmResponseCache.created_at < cutoff)
    result = db.execute(stmt)
    return int(result.rowcount or 0)


def run_purge(*, dry_run: bool, older_than_days: int | None = None) -> PurgeResult:
    """Purge LlmResponseCache rows. Returns counts + log path.

    Caller is responsible for setting ``DATABASE_URL`` before invoking when
    targeting production. The function itself does not enforce that
    requirement — the CLI wrapper does.
    """
    mode = "dryrun" if dry_run else "apply"
    log_path = _new_log_path(mode)
    with SessionLocal() as db:
        matched = _count_matching(db, older_than_days)
        if dry_run:
            deleted = 0
        else:
            deleted = _delete_matching(db, older_than_days)
            db.commit()
    with log_path.open("w", encoding="utf-8") as f:
        f.write(
            f"purge_llm_cache run at {datetime.now(UTC).isoformat()}\n"
            f"mode: {mode}\n"
            f"older_than_days filter: {older_than_days}\n"
            f"matched rows: {matched}\n"
            f"deleted rows: {deleted}\n"
        )
    return PurgeResult(
        matched=matched,
        deleted=deleted,
        log_path=log_path,
        older_than_days=older_than_days,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Count matching rows; do not delete.",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete matching rows. Requires DATABASE_URL env var.",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=None,
        help="Only purge entries older than N days (default: purge all).",
    )
    args = parser.parse_args(argv)

    if args.apply and not os.environ.get("DATABASE_URL"):
        print(
            "ERROR: --apply requires DATABASE_URL env var to be set "
            "(production safety guard). Set it explicitly before running, "
            "and unset it after.",
            file=sys.stderr,
        )
        return 2

    result = run_purge(
        dry_run=args.dry_run,
        older_than_days=args.older_than_days,
    )

    filter_desc = (
        f" (older than {result.older_than_days} days)"
        if result.older_than_days is not None
        else ""
    )
    if args.dry_run:
        print(
            f"[dry-run] Would delete {result.matched} rows{filter_desc}. "
            f"No changes made. Log: {result.log_path}"
        )
    else:
        print(
            f"[apply] Deleted {result.deleted} of {result.matched} rows"
            f"{filter_desc}. Log: {result.log_path}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
