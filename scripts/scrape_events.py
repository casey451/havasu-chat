"""
Scrape event sources into the contributions queue (Phase 9b).

Usage:
  python -m scripts.scrape_events --source chamber
  python -m scripts.scrape_events --source go_lake_havasu
  python -m scripts.scrape_events --all
  python -m scripts.scrape_events --all --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.approval_service import (  # noqa: E402
    approve_contribution_as_event,
    should_auto_approve_event,
)
from app.db import contribution_store as cs  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.events.dedup import (  # noqa: E402
    find_duplicate,
    merge_scraper_into_event,
    resolve_venue_entity_id,
)
from app.events.scrapers import SOURCE_REGISTRY  # noqa: E402
from app.events.scrapers.base import (  # noqa: E402
    EventPayload,
    event_payload_to_contribution,
    normalize_event_title,
)
from app.schemas.contribution import EventApprovalFields  # noqa: E402


def _persist_payload(
    db,
    payload: EventPayload,
    *,
    scrape_source: str,
    dry_run: bool,
) -> str:
    """Returns action label: created | merged | skipped_duplicate | auto_approved."""
    venue_id = payload.venue_entity_id or resolve_venue_entity_id(
        db, payload.venue_name
    )
    if not payload.start_date or not payload.start_time:
        return "skipped_incomplete"
    dup = find_duplicate(
        db,
        venue_entity_id=venue_id,
        start_date=payload.start_date,
        start_time_obj=payload.start_time,
        normalized_title=normalize_event_title(payload.name),
    )
    if dup is not None:
        if dry_run:
            return "would_merge"
        merge_scraper_into_event(db, dup, payload, scrape_source=scrape_source)
        db.commit()
        return "merged"

    if dry_run:
        return "would_create"

    contrib_body = event_payload_to_contribution(payload, scrape_source=scrape_source)
    if cs.has_pending_or_approved_duplicate_url(db, contrib_body.source_url):
        return "skipped_duplicate"

    created = cs.create_contribution(db, contrib_body)
    if should_auto_approve_event(created):
        fields = EventApprovalFields(
            title=payload.name,
            description=(payload.description or contrib_body.submission_notes or ""),
            date=payload.start_date,
            end_date=payload.end_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            location_name=payload.venue_name or "Lake Havasu",
            event_url=str(contrib_body.submission_url or payload.event_url or ""),
            source_url=contrib_body.source_url,
        )
        approve_contribution_as_event(
            db, created.id, fields, list(payload.tags or [])
        )
        return "auto_approved"
    return "queued"


def run_source(source_key: str, *, dry_run: bool) -> dict[str, int]:
    client_cls = SOURCE_REGISTRY[source_key]
    client = client_cls()
    counts: dict[str, int] = {}
    payloads = client.run({"today": date.today()})
    for payload in payloads:
        try:
            with SessionLocal() as db:
                action = _persist_payload(
                    db, payload, scrape_source=client.scrape_source, dry_run=dry_run
                )
        except Exception as exc:
            print(f"error: {source_key} payload {payload.name!r}: {exc}", file=sys.stderr)
            action = "error"
        counts[action] = counts.get(action, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape event sources")
    parser.add_argument("--source", action="append", dest="sources", metavar="SOURCE")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.all:
        sources = list(SOURCE_REGISTRY.keys())
    elif args.sources:
        sources = args.sources
    else:
        parser.error("Specify --source SOURCE or --all")

    unknown = [s for s in sources if s not in SOURCE_REGISTRY]
    if unknown:
        parser.error(f"unknown sources: {', '.join(unknown)}")

    exit_code = 0
    for key in sources:
        print(f"=== {key} ===")
        try:
            counts = run_source(key, dry_run=args.dry_run)
        except Exception as exc:
            print(f"fatal: {key}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        for action, n in sorted(counts.items()):
            print(f"  {action}: {n}")
        total = sum(counts.values())
        print(f"  total payloads: {total}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
