"""Backfill ``Provider.hours_structured`` from ``google_hours``.

One-shot migration for rows imported via Google Places where
``google_hours`` is populated but ``hours_structured`` is NULL.

  python -m scripts.backfill_hours_structured --dry-run
  python -m scripts.backfill_hours_structured --apply

Logs to ``backfill_hours_structured.log`` in the repo root.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.hours_helper import places_hours_to_structured  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

LOG_PATH = Path(__file__).resolve().parents[1] / "backfill_hours_structured.log"
BATCH_SIZE = 100
SAMPLE_LIMIT = 5


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _candidates(db) -> list[Provider]:
    stmt = (
        select(Provider)
        .where(Provider.hours_structured.is_(None))
        .where(Provider.google_hours.isnot(None))
        .order_by(Provider.id)
    )
    return list(db.execute(stmt).scalars().all())


def _convert(google_hours: dict) -> dict | None:
    converted = places_hours_to_structured(google_hours)
    return converted if converted else None


def run(*, apply: bool) -> tuple[int, int, int]:
    """Return ``(total_candidates, convertible, applied)``."""
    total = convertible = applied = skipped = 0
    samples_shown = 0

    with SessionLocal() as db:
        rows = _candidates(db)
        total = len(rows)
        logging.info("Found %d providers with google_hours and NULL hours_structured", total)

        batch: list[Provider] = []
        for provider in rows:
            gh = provider.google_hours
            if not isinstance(gh, dict):
                skipped += 1
                continue
            structured = _convert(gh)
            if not structured:
                skipped += 1
                continue
            convertible += 1

            if samples_shown < SAMPLE_LIMIT:
                logging.info(
                    "Sample %d slug=%s before=NULL after=%s",
                    samples_shown + 1,
                    provider.slug,
                    json.dumps(structured, sort_keys=True),
                )
                samples_shown += 1

            if apply:
                provider.hours_structured = structured
                batch.append(provider)
                if len(batch) >= BATCH_SIZE:
                    db.add_all(batch)
                    db.commit()
                    applied += len(batch)
                    logging.info(
                        "Committed batch of %d rows (total applied=%d)", len(batch), applied
                    )
                    batch.clear()

        if apply and batch:
            db.add_all(batch)
            db.commit()
            applied += len(batch)
            logging.info("Committed final batch of %d rows", len(batch))

    logging.info(
        "Backfill complete: total=%d convertible=%d skipped=%d applied=%d mode=%s",
        total,
        convertible,
        skipped,
        applied,
        "apply" if apply else "dry-run",
    )
    if apply:
        assert applied == convertible, f"applied ({applied}) != convertible ({convertible})"
    else:
        assert applied == 0, f"dry-run must not persist rows (applied={applied})"
    return total, convertible, applied


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default).")
    mode.add_argument("--apply", action="store_true", help="Persist updates.")
    return p.parse_args()


def main() -> int:
    _configure_logging()
    args = _parse_args()
    run(apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
