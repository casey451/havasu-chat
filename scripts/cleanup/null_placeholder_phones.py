"""One-shot cleanup: null Provider.phone for any NANP-reserved 555-01XX value.

Idempotent — safe to re-run. Logs every change with provider id and old value
to a timestamped file in scripts/cleanup/logs/.

Usage:
    python -m scripts.cleanup.null_placeholder_phones --dry-run
    python -m scripts.cleanup.null_placeholder_phones --apply
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Provider
from app.home.queries import _PLACEHOLDER_PHONE_RE


@dataclass(frozen=True)
class PlaceholderCleanupResult:
    matched: int
    updated: int
    log_path: Path


def _nanp_digits10(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return digits


def is_placeholder_nanp_phone(raw: str | None) -> bool:
    """True when ``raw`` normalizes to (NXX) 555-01XX."""
    d = _nanp_digits10(raw)
    return bool(d and _PLACEHOLDER_PHONE_RE.match(d))


def run_placeholder_cleanup(db: Session, *, apply: bool, log_dir: Path) -> PlaceholderCleanupResult:
    """Find providers with placeholder phones; optionally null them. Always writes a log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"placeholder_phones_{ts}.log"

    rows = db.scalars(select(Provider).where(Provider.phone.isnot(None))).all()
    matches = [p for p in rows if is_placeholder_nanp_phone(p.phone)]

    updated = 0
    with log_path.open("w", encoding="utf-8") as logf:
        for p in matches:
            old = p.phone
            logf.write(f"id={p.id} old_phone={old!r}\n")
            if apply:
                p.phone = None
                updated += 1
        logf.flush()

    if apply and updated:
        db.commit()

    return PlaceholderCleanupResult(matched=len(matches), updated=updated, log_path=log_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Null NANP 555-01XX placeholder phones on providers."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="Report matches only; do not update rows."
    )
    group.add_argument("--apply", action="store_true", help="Set matching phones to NULL.")
    args = parser.parse_args()

    apply = bool(args.apply)
    log_dir = Path(__file__).resolve().parent / "logs"
    db = SessionLocal()
    try:
        result = run_placeholder_cleanup(db, apply=apply, log_dir=log_dir)
        mode = "apply" if apply else "dry-run"
        print(
            f"[{mode}] matched={result.matched} updated={result.updated} log={result.log_path}",
            file=sys.stderr,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
