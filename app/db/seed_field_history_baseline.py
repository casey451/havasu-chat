"""
Write baseline field_history rows (state='established', source='seed') for tracked
fields on every provider, program, and event.

Idempotent on (entity_type, entity_id, field_name, state='established'). Does not
mutate provider/program/event rows.

Usage:
  python -m app.db.seed_field_history_baseline
"""
from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FieldHistory

from app.core.field_tracking import (
    EVENT_TRACKED_FIELDS,
    PROGRAM_TRACKED_FIELDS,
    PROVIDER_TRACKED_FIELDS,
)


def _serialize_new_value(val: Any) -> str | None:
    """Store in field_history.new_value: null for missing; scalars as plain text; JSON only for list/dict."""
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return json.dumps(val, default=str, ensure_ascii=False)
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (date, datetime, time)):
        return val.isoformat()
    return str(val)


def _serialize_field(entity: Any, entity_label: str, entity_id: str, field_name: str) -> tuple[str | None, str | None]:
    """Return (new_value or None, error_message or None)."""
    try:
        raw = getattr(entity, field_name)
    except AttributeError as e:
        return None, f"{entity_label} id={entity_id} field={field_name!r}: missing attribute: {e}"
    try:
        return _serialize_new_value(raw), None
    except (TypeError, ValueError) as e:
        return None, f"{entity_label} id={entity_id} field={field_name!r}: serialize failed: {e}"


@dataclass
class SeedFieldHistoryBaselineResult:
    providers_processed: int = 0
    programs_processed: int = 0
    events_processed: int = 0
    rows_created_provider: int = 0
    rows_created_program: int = 0
    rows_created_event: int = 0
    rows_skipped: int = 0
    field_history_count_before: int = 0
    field_history_count_after: int = 0
    serialization_failures: list[str] = field(default_factory=list)


def _load_established_keys(db: Session) -> set[tuple[str, str, str]]:
    rows = db.execute(
        select(FieldHistory.entity_type, FieldHistory.entity_id, FieldHistory.field_name).where(
            FieldHistory.state == "established",
        )
    ).all()
    return {(str(r[0]), str(r[1]), str(r[2])) for r in rows}


def seed_field_history_baseline(db: Session) -> SeedFieldHistoryBaselineResult:
    from app.db.models import Event, Program, Provider

    result = SeedFieldHistoryBaselineResult()
    result.field_history_count_before = db.query(FieldHistory).count()
    existing = _load_established_keys(db)
    now = datetime.now(UTC).replace(tzinfo=None)

    mappings: list[dict[str, Any]] = []

    def flush_if_large() -> None:
        if len(mappings) >= 400:
            db.bulk_insert_mappings(FieldHistory, mappings)
            db.commit()
            mappings.clear()

    providers = list(db.scalars(select(Provider).order_by(Provider.id)).all())
    result.providers_processed = len(providers)
    for p in providers:
        for fn in PROVIDER_TRACKED_FIELDS:
            key = ("provider", p.id, fn)
            if key in existing:
                result.rows_skipped += 1
                continue
            nv, err = _serialize_field(p, "provider", p.id, fn)
            if err:
                result.serialization_failures.append(err)
                continue
            mappings.append(
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "provider",
                    "entity_id": p.id,
                    "field_name": fn,
                    "old_value": None,
                    "new_value": nv,
                    "source": "seed",
                    "submitted_by_session": None,
                    "submitted_at": now,
                    "state": "established",
                    "confirmations": 0,
                    "disputes": 0,
                    "resolution_deadline": None,
                    "resolved_at": None,
                    "resolved_value": None,
                    "resolution_source": None,
                }
            )
            existing.add(key)
            result.rows_created_provider += 1
            flush_if_large()

    programs = list(db.scalars(select(Program).order_by(Program.id)).all())
    result.programs_processed = len(programs)
    for p in programs:
        for fn in PROGRAM_TRACKED_FIELDS:
            key = ("program", p.id, fn)
            if key in existing:
                result.rows_skipped += 1
                continue
            nv, err = _serialize_field(p, "program", p.id, fn)
            if err:
                result.serialization_failures.append(err)
                continue
            mappings.append(
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "program",
                    "entity_id": p.id,
                    "field_name": fn,
                    "old_value": None,
                    "new_value": nv,
                    "source": "seed",
                    "submitted_by_session": None,
                    "submitted_at": now,
                    "state": "established",
                    "confirmations": 0,
                    "disputes": 0,
                    "resolution_deadline": None,
                    "resolved_at": None,
                    "resolved_value": None,
                    "resolution_source": None,
                }
            )
            existing.add(key)
            result.rows_created_program += 1
            flush_if_large()

    events = list(db.scalars(select(Event).order_by(Event.id)).all())
    result.events_processed = len(events)
    for e in events:
        for fn in EVENT_TRACKED_FIELDS:
            key = ("event", e.id, fn)
            if key in existing:
                result.rows_skipped += 1
                continue
            nv, err = _serialize_field(e, "event", e.id, fn)
            if err:
                result.serialization_failures.append(err)
                continue
            mappings.append(
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "event",
                    "entity_id": e.id,
                    "field_name": fn,
                    "old_value": None,
                    "new_value": nv,
                    "source": "seed",
                    "submitted_by_session": None,
                    "submitted_at": now,
                    "state": "established",
                    "confirmations": 0,
                    "disputes": 0,
                    "resolution_deadline": None,
                    "resolved_at": None,
                    "resolved_value": None,
                    "resolution_source": None,
                }
            )
            existing.add(key)
            result.rows_created_event += 1
            flush_if_large()

    if mappings:
        db.bulk_insert_mappings(FieldHistory, mappings)
        db.commit()

    result.field_history_count_after = db.query(FieldHistory).count()
    _print_report(result)
    return result


def _print_report(result: SeedFieldHistoryBaselineResult) -> None:
    print("=== Seed field_history baseline (established / seed) ===")
    print(f"entities processed: providers={result.providers_processed}  programs={result.programs_processed}  events={result.events_processed}")
    print(f"rows created: provider={result.rows_created_provider}  program={result.rows_created_program}  event={result.rows_created_event}")
    print(f"rows skipped (idempotent — established key already present): {result.rows_skipped}")
    print(f"field_history total rows before: {result.field_history_count_before}")
    print(f"field_history total rows after: {result.field_history_count_after}")
    if result.serialization_failures:
        print(f"serialization / attribute issues: {len(result.serialization_failures)}")
        for line in result.serialization_failures[:50]:
            print(f"  {line}")
        if len(result.serialization_failures) > 50:
            print("  ...")


def main(argv: list[str] | None = None) -> int:
    from app.bootstrap_env import ensure_dotenv_loaded
    from app.db.database import SessionLocal, init_db

    ensure_dotenv_loaded()
    parser = argparse.ArgumentParser(description="Seed field_history established baselines")
    parser.parse_args(argv)
    init_db()
    with SessionLocal() as db:
        seed_field_history_baseline(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
