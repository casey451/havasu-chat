"""
Google bulk import from enrichment JSONL (Phase 8.11b, Approach X).

Writes directly to ``Provider`` — no contribution queue. Does **not** compute
embeddings (Phase 8.11c).

**Expected JSONL row shape** (one JSON object per line; extra keys ignored):

- **Required:** ``google_place_id``, ``provider_name``, ``category`` (non-empty strings).
- **Optional:** ``description``, ``address``, ``phone``, ``email``, ``website``,
  ``facebook``, ``hours``, ``hours_structured``, ``lat``, ``lng``,
  ``match_confidence``, ``enrichment_version``, ``raw_enrichment_json`` — ``null`` in
  JSON becomes ``None`` in the DB when the key is present.

**Idempotency (per run, file order):**

1. Validate required fields; skip row if any missing/empty.
2. **First occurrence wins** for duplicate ``google_place_id`` within the same file;
   later lines with the same id are skipped (``skipped_duplicate_in_file``).
3. Match existing row by ``google_place_id``; if found, update (see below).
4. Else match by **normalized name** (same algorithm as ``seed_providers._norm_provider_name``);
   if found, update and set ``google_place_id`` from the row.
5. Else insert a new ``Provider`` with ``source="google_bulk_import"``.

**Update behavior:** Only enrichment-related columns are written; see
:func:`_apply_row_to_provider`. Never touches ``embedding``, ``id``, ``created_at``,
``draft``, ``verified``, ``is_active``, ``pending_review``, ``tier``,
``sponsored_until``, ``featured_description``, ``admin_review_by``.

**Commits:** Every 100 successful upserts (insert or update), plus a final commit.
``dry_run=True`` performs lookups and counters only — no ``commit``/``add``.

``parse_jsonl`` returns one dict per non-empty line that parses as a JSON object;
malformed lines are printed to stderr and skipped (no exception).
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Provider
from app.db.seed_providers import _norm_provider_name

_SOURCE = "google_bulk_import"

# Columns we may set from JSON (insert or update). Keys not in row leave insert defaults / unchanged.
_KNOWN_KEYS = frozenset(
    {
        "google_place_id",
        "provider_name",
        "category",
        "description",
        "address",
        "phone",
        "email",
        "website",
        "facebook",
        "hours",
        "hours_structured",
        "lat",
        "lng",
        "match_confidence",
        "enrichment_version",
        "raw_enrichment_json",
    }
)


@dataclass
class IngestionCounters:
    fetched_rows: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_missing_required: int = 0
    skipped_duplicate_in_file: int = 0
    errors: int = 0


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file, return a list of dicts. Each line is one JSON object.

    Malformed lines are logged to stderr and skipped; does not raise.
    """
    out: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            print(f"parse_jsonl: skip line {i}: {e}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            print(f"parse_jsonl: skip line {i}: expected object, got {type(obj).__name__}", file=sys.stderr)
            continue
        out.append(obj)
    return out


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _required_ok(row: dict[str, Any]) -> bool:
    g = row.get("google_place_id")
    g_ok = isinstance(g, str) and g.strip() != ""
    n = row.get("provider_name")
    n_ok = isinstance(n, str) and n.strip() != ""
    c = row.get("category")
    c_ok = isinstance(c, str) and c.strip() != ""
    return bool(g_ok and n_ok and c_ok)


def _only_known_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k in _KNOWN_KEYS}


def _find_by_google_place_id(db: Session, place_id: str) -> Provider | None:
    return db.scalars(select(Provider).where(Provider.google_place_id == place_id).limit(1)).first()


def _find_by_normalized_name(db: Session, provider_name: str) -> Provider | None:
    target = _norm_provider_name(provider_name)
    for p in db.query(Provider).all():
        if _norm_provider_name(p.provider_name) == target:
            return p
    return None


def _apply_row_to_provider(p: Provider, row: dict[str, Any]) -> None:
    """Apply only JSON-overwritable fields; never protected columns."""
    data = _only_known_keys(row)
    for key in _KNOWN_KEYS:
        if key not in data:
            continue
        val = data[key]
        if key == "provider_name" and val is not None:
            p.provider_name = str(val).strip()
        elif key == "category" and val is not None:
            p.category = str(val).strip()
        elif key == "description":
            p.description = val if val is None else str(val)
        elif key == "address":
            p.address = val if val is None else str(val)
        elif key == "phone":
            p.phone = val if val is None else str(val)
        elif key == "email":
            p.email = val if val is None else str(val)
        elif key == "website":
            p.website = val if val is None else str(val)
        elif key == "facebook":
            p.facebook = val if val is None else str(val)
        elif key == "hours":
            p.hours = val if val is None else str(val)
        elif key == "hours_structured":
            p.hours_structured = val if val is None or isinstance(val, dict) else val
        elif key == "lat":
            p.lat = None if val is None else float(val)
        elif key == "lng":
            p.lng = None if val is None else float(val)
        elif key == "google_place_id":
            p.google_place_id = val if val is None else str(val).strip()
        elif key == "match_confidence":
            p.match_confidence = None if val is None else float(val)
        elif key == "enrichment_version":
            p.enrichment_version = val if val is None else str(val)
        elif key == "raw_enrichment_json":
            p.raw_enrichment_json = val if val is None or isinstance(val, dict) else val
    p.updated_at = _now()


def _new_provider_from_row(row: dict[str, Any]) -> Provider:
    d = _only_known_keys(row)
    now = _now()
    p = Provider(
        id=str(uuid.uuid4()),
        provider_name=str(d["provider_name"]).strip(),
        category=str(d["category"]).strip(),
        source=_SOURCE,
        created_at=now,
        updated_at=now,
        draft=False,
        verified=False,
        is_active=True,
        pending_review=False,
    )
    _apply_row_to_provider(p, row)
    p.source = _SOURCE
    p.created_at = now
    return p


def _process_one_row(
    row: dict[str, Any],
    db: Session,
    dry_run: bool,
    counters: IngestionCounters,
) -> None:
    gpid = str(row.get("google_place_id", "")).strip()

    by_id = _find_by_google_place_id(db, gpid)
    if by_id is not None:
        if dry_run:
            counters.updated += 1
            return
        _apply_row_to_provider(by_id, row)
        db.add(by_id)
        counters.updated += 1
        return

    by_name = _find_by_normalized_name(db, str(row.get("provider_name", "")))
    if by_name is not None:
        if dry_run:
            counters.updated += 1
            return
        _apply_row_to_provider(by_name, row)
        db.add(by_name)
        counters.updated += 1
        return

    if dry_run:
        counters.inserted += 1
        return
    p = _new_provider_from_row(row)
    db.add(p)
    counters.inserted += 1


def run_ingest(
    path: Path,
    db: Session,
    *,
    dry_run: bool = False,
) -> IngestionCounters:
    """Read the JSONL file, upsert ``Provider`` rows, return counters.

    When ``dry_run=True``, no database writes (no add/commit).
    """
    rows = parse_jsonl(path)
    counters = IngestionCounters()
    counters.fetched_rows = len(rows)

    seen_gpid: set[str] = set()
    since_commit = 0

    for row in rows:
        if not _required_ok(row):
            counters.skipped_missing_required += 1
            continue
        gpid = str(row["google_place_id"]).strip()
        if gpid in seen_gpid:
            counters.skipped_duplicate_in_file += 1
            continue
        seen_gpid.add(gpid)

        try:
            if dry_run:
                _process_one_row(row, db, True, counters)
            else:
                with db.begin_nested():
                    _process_one_row(row, db, False, counters)
                since_commit += 1
                if since_commit >= 100:
                    db.commit()
                    since_commit = 0
        except Exception as e:
            counters.errors += 1
            print(
                f"error: google_place_id={gpid!r} {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            traceback.print_exc()

    if not dry_run and since_commit:
        db.commit()

    return counters
