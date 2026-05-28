"""Backfill ``Provider.google_photo_urls`` from ``google_photo_refs``.

One-shot migration for rows where Places photo refs are stored but resolved
media URLs are missing. Resolves each ref via ``places.photos.getMedia`` and
stores parallel long-lived URLs without overwriting raw refs.

  python -m scripts.backfill_photo_urls --dry-run
  python -m scripts.backfill_photo_urls --apply

Logs to ``backfill_photo_urls.log`` in the repo root.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import or_, select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.providers.photo_urls import resolve_photo_ref  # noqa: E402

LOG_PATH = Path(__file__).resolve().parents[1] / "backfill_photo_urls.log"
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
        .where(Provider.google_photo_refs.isnot(None))
        .where(
            or_(
                Provider.google_photo_urls.is_(None),
                Provider.google_photo_urls == [],  # type: ignore[arg-type]
            )
        )
        .order_by(Provider.id)
    )
    return list(db.execute(stmt).scalars().all())


def _resolve_refs(refs: list[str]) -> tuple[list[str | None], int, int]:
    """Return (parallel urls, resolved_count, failed_count)."""
    urls: list[str | None] = []
    resolved = failed = 0
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            urls.append(None)
            failed += 1
            continue
        url = resolve_photo_ref(ref)
        urls.append(url)
        if url:
            resolved += 1
        else:
            failed += 1
    return urls, resolved, failed


def run(*, apply: bool) -> tuple[int, int, int, int]:
    """Return ``(total, convertible, resolved_refs, failed_refs)``."""
    total = convertible = resolved_refs = failed_refs = applied = 0
    samples_shown = 0

    with SessionLocal() as db:
        rows = _candidates(db)
        total = len(rows)
        logging.info(
            "Found %d providers with google_photo_refs and missing google_photo_urls",
            total,
        )

        batch: list[Provider] = []
        for provider in rows:
            refs = provider.google_photo_refs
            if not isinstance(refs, list) or not refs:
                continue
            convertible += 1
            urls, row_resolved, row_failed = _resolve_refs(refs)
            resolved_refs += row_resolved
            failed_refs += row_failed

            if samples_shown < SAMPLE_LIMIT:
                sample_pairs = [
                    (r, u)
                    for r, u in zip(refs, urls, strict=False)
                    if u is not None
                ][:3]
                logging.info(
                    "Sample %d slug=%s pairs=%s",
                    samples_shown + 1,
                    provider.slug,
                    json.dumps(sample_pairs),
                )
                samples_shown += 1

            if apply:
                provider.google_photo_urls = urls
                batch.append(provider)
                if len(batch) >= BATCH_SIZE:
                    db.add_all(batch)
                    db.commit()
                    applied += len(batch)
                    logging.info(
                        "Committed batch of %d rows (total applied=%d)",
                        len(batch),
                        applied,
                    )
                    batch.clear()

        if apply and batch:
            db.add_all(batch)
            db.commit()
            applied += len(batch)
            logging.info("Committed final batch of %d rows", len(batch))

    logging.info(
        "Backfill complete: total=%d convertible=%d resolved=%d failed=%d "
        "applied=%d mode=%s",
        total,
        convertible,
        resolved_refs,
        failed_refs,
        applied,
        "apply" if apply else "dry-run",
    )
    if apply:
        assert applied == convertible, f"applied ({applied}) != convertible ({convertible})"
    else:
        assert applied == 0, f"dry-run must not persist rows (applied={applied})"
    return total, convertible, resolved_refs, failed_refs


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
