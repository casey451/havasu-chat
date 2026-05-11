"""Idempotently upsert a validated enrichment CSV into ``providers``.

USAGE
-----
    python scripts/ingest/ingest_enrichment_csv.py path/to/filled.csv
    python scripts/ingest/ingest_enrichment_csv.py path/to/filled.csv --dry-run

NATURAL KEY
-----------
Each row is matched to an existing Provider by case-insensitive
``provider_name`` AND case-insensitive ``category``. The Provider model
has no DB-level uniqueness constraint on ``(provider_name, category)``;
this is a deliberate operator-side choice. We picked that pair because:

* The operator is dealing with a small, hand-curated enrichment batch.
* ``google_place_id`` is the canonical natural key for Places-sourced
  rows but isn't collected on this template (the operator works from
  phone calls and site visits, not Places data).
* ``provider_name`` alone collides across categories (a single name can
  appear as both ``food_drink`` and ``event_venue``).

If multiple providers match the natural key, ingest fails the row
(better to surface the ambiguity than guess).

BEHAVIOR
--------
* Always runs the validator first; refuses to proceed if validation
  fails.
* For each row:
  - INSERT if no Provider matches the natural key.
  - UPDATE if exactly one Provider matches and at least one enrichment
    field would change.
  - SKIP-NOOP if exactly one match and no fields differ (idempotent).
* Always writes ``last_verified_at`` and ``verification_method``. The
  CSV's ``last_verified_at`` is parsed via ``datetime.fromisoformat``
  and converted to ``LAKE_HAVASU_TZ`` so the value is timezone-aware
  before binding (the column raises on naive datetimes).
* Wraps the entire batch in a single transaction. Any per-row
  exception rolls the whole batch back with a clear error.
* ``--dry-run`` runs the full pipeline but rolls back instead of
  committing.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Project-root on sys.path so this script can be invoked either as
#   python scripts/ingest/ingest_enrichment_csv.py ...
# or as
#   python -m scripts.ingest.ingest_enrichment_csv ...
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func  # noqa: E402  -- requires _ROOT on sys.path (above)
from sqlalchemy.orm import Session  # noqa: E402

from app.core.timezone import LAKE_HAVASU_TZ  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402
from scripts.ingest.validate_enrichment_csv import (  # noqa: E402
    print_report,
    validate_csv,
)

# Enrichment fields the operator owns via this template. The script writes
# only these (plus ``last_verified_at`` / ``verification_method``); any
# other Provider columns on an existing row are left alone.
ENRICHMENT_FIELDS: tuple[str, ...] = (
    "address",
    "phone",
    "email",
    "website",
    "hours",
    "description",
)

def _to_aware(raw: str) -> datetime:
    """Parse the CSV's ``last_verified_at`` to a TZ-aware Lake Havasu dt.

    The validator already confirmed the string parses; this is the
    binding-side conversion. Naive inputs (no tzinfo) are interpreted as
    Lake Havasu local — the operator entry guidance always specifies an
    offset, but be lenient if a row slipped through.
    """
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LAKE_HAVASU_TZ)
    return dt.astimezone(LAKE_HAVASU_TZ)


def _normalize_phone(raw: str) -> str:
    """Strip to the 10-digit NANP form. Validator already enforced shape."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _row_to_payload(row: dict[str, str]) -> dict[str, object]:
    """Transform one validated CSV row into a dict of Provider attrs.

    Only fields touched by the enrichment workflow are returned. The
    caller decides whether to apply via INSERT or UPDATE.
    """
    return {
        "provider_name": (row.get("provider_name") or "").strip(),
        "category": (row.get("category") or "").strip(),
        "address": (row.get("address") or "").strip(),
        "phone": _normalize_phone(row.get("phone") or ""),
        "email": (row.get("owner_email") or "").strip(),
        "website": (row.get("website") or "").strip() or None,
        "hours": (row.get("hours") or "").strip() or None,
        "description": (row.get("hava_voice_description") or "").strip(),
        "last_verified_at": _to_aware(row.get("last_verified_at") or ""),
        "verification_method": (row.get("verification_method") or "").strip(),
    }


def _find_existing(db: Session, name: str, category: str) -> Provider | None:
    """Look up by case-insensitive (provider_name, category).

    Returns ``None`` for no match. Raises if multiple providers match
    (caller turns this into a per-row failure so the operator sees it).
    """
    matches: list[Provider] = (
        db.query(Provider)
        .filter(
            func.lower(Provider.provider_name) == name.lower(),
            func.lower(Provider.category) == category.lower(),
        )
        .all()
    )
    if not matches:
        return None
    if len(matches) > 1:
        ids = ", ".join(p.id for p in matches)
        raise RuntimeError(
            f"natural key (name={name!r}, category={category!r}) matched "
            f"{len(matches)} providers: {ids}"
        )
    return matches[0]


def _diff_fields(existing: Provider, payload: dict[str, object]) -> list[str]:
    """Return the list of field names where existing != payload."""
    changed: list[str] = []
    for field_name in (
        *ENRICHMENT_FIELDS,
        "last_verified_at",
        "verification_method",
    ):
        new = payload.get(field_name)
        old = getattr(existing, field_name, None)
        # last_verified_at is TZ-aware on both sides; compare directly.
        if new != old:
            changed.append(field_name)
    return changed


def _iter_data_rows(reader: csv.DictReader) -> Iterable[tuple[int, dict[str, str]]]:
    """Mirrors the validator's row iteration — skip comments and blanks."""
    for idx, row in enumerate(reader, start=2):
        first_val = (row.get("provider_name") or "").lstrip()
        if first_val.startswith("#"):
            continue
        if not any((v or "").strip() for v in row.values()):
            continue
        yield idx, row


def ingest_csv(csv_path: Path, *, dry_run: bool, db: Session) -> int:
    """Run the upsert. Returns the number of error rows (0 = clean run)."""
    n_insert = 0
    n_update = 0
    n_noop = 0
    n_error = 0

    print(f"ingesting: {csv_path}{' (dry-run)' if dry_run else ''}")
    print("-" * 64)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row_number, row in _iter_data_rows(reader):
            try:
                payload = _row_to_payload(row)
                existing = _find_existing(
                    db, payload["provider_name"], payload["category"]
                )
                if existing is None:
                    slug = derive_provider_slug(db, payload["provider_name"])
                    new_row = Provider(
                        provider_name=payload["provider_name"],
                        category=payload["category"],
                        slug=slug,
                        address=payload["address"],
                        phone=payload["phone"],
                        email=payload["email"],
                        website=payload["website"],
                        hours=payload["hours"],
                        description=payload["description"],
                        last_verified_at=payload["last_verified_at"],
                        verification_method=payload["verification_method"],
                        source="operator_enrichment",
                    )
                    db.add(new_row)
                    db.flush()  # populate id without committing
                    n_insert += 1
                    print(
                        f"  INSERT  row {row_number:>3}  id={new_row.id}  "
                        f"{payload['provider_name']}"
                    )
                    continue

                changed = _diff_fields(existing, payload)
                if not changed:
                    n_noop += 1
                    print(
                        f"  SKIP-NOOP  row {row_number:>3}  id={existing.id}  "
                        f"{payload['provider_name']}"
                    )
                    continue

                for field_name in (
                    *ENRICHMENT_FIELDS,
                    "last_verified_at",
                    "verification_method",
                ):
                    setattr(existing, field_name, payload[field_name])
                db.flush()
                n_update += 1
                print(
                    f"  UPDATE  row {row_number:>3}  id={existing.id}  "
                    f"{payload['provider_name']}  changed={','.join(changed)}"
                )
            except Exception as exc:
                n_error += 1
                print(f"  ERROR  row {row_number:>3}  {exc!r}")
                # Bail at first row error — caller will rollback the batch.
                raise

    print("-" * 64)
    summary = (
        f"summary: {n_insert} insert, {n_update} update, "
        f"{n_noop} noop, {n_error} error"
    )
    print(summary)
    return n_error


def run(csv_path: Path, *, dry_run: bool) -> int:
    """Top-level orchestration: validate -> ingest -> commit/rollback."""
    report = validate_csv(csv_path)
    print_report(report)
    if not report.ok:
        print("ingest aborted — fix validation errors and re-run")
        return 1

    db = SessionLocal()
    try:
        errors = ingest_csv(csv_path, dry_run=dry_run, db=db)
        if errors:
            db.rollback()
            print("rolled back due to row error(s)")
            return 1
        if dry_run:
            db.rollback()
            print("dry-run complete — no changes committed")
            return 0
        db.commit()
        print("committed.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"transaction rolled back due to: {exc!r}")
        return 1
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upsert a validated enrichment CSV into Provider rows.",
    )
    parser.add_argument("csv_path", type=Path, help="path to filled enrichment CSV")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the full pipeline without committing",
    )
    args = parser.parse_args(argv)
    return run(args.csv_path, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
