"""
Orchestration: golakehavasu.com -> contributions queue, via the shared event
reconciler (Phase: CVB events).

``scripts/golakehavasu_pull.py`` is a thin CLI over :func:`run_pull`.

Flow per event URL:
  parse -> build EventPayload -> reconcile_event(db, payload):
    * insert     -> create contribution (go_lake_havasu) + auto-approve as Event
    * update     -> same source_url already present; merge richer fields onto it
    * duplicate  -> cross-source match; merge useful fields + provenance, no new row
    * ambiguous  -> create contribution but leave PENDING for human review

golakehavasu is a high-trust CVB source and is already in
``auto_approve_event_sources`` + ``ContributionSource``; duplicates are caught
by the reconciler before they can double-book the calendar.
"""

from __future__ import annotations

import sys
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.contrib.approval_service import (
    approve_contribution_as_event,
    should_auto_approve_event,
)
from app.contrib.event_reconciler import (
    log_ambiguous_reconcile,
    reconcile_event,
)
from app.contrib.golakehavasu import (
    REQUEST_TIMEOUT,
    SOURCE_NAME,
    USER_AGENT,
    GoLakeHavasuEvent,
    fetch_and_parse_event,
    fetch_sitemap_urls,
    normalize_to_contribution,
)
from app.db import contribution_store as cs
from app.db.database import SessionLocal
from app.db.models import Event
from app.events.scrapers.base import EventPayload
from app.schemas.contribution import EventApprovalFields

# Event columns the reconciler is allowed to merge onto an existing row.
_MERGEABLE_EVENT_FIELDS = frozenset(
    {
        "source",
        "title",
        "normalized_title",
        "description",
        "location_name",
        "location_normalized",
        "event_url",
        "source_url",
        "end_time",
        "end_date",
    }
)


def _to_event_payload(ge: GoLakeHavasuEvent) -> EventPayload:
    return EventPayload(
        name=ge.title,
        entity_type="event",
        source=SOURCE_NAME,
        start_date=ge.start_date,
        end_date=(ge.end_date if ge.end_date > ge.start_date else None),
        start_time=ge.start_time,
        end_time=ge.end_time,
        venue_name=ge.venue_name,
        address=ge.venue_address,
        description=(ge.description or ""),
        event_url=_public_event_url(ge),
        source_stable_url=ge.url,
        lat=ge.lat,
        lng=ge.lng,
        tags=["events"],
        category_slug="events",
    )


def _public_event_url(ge: GoLakeHavasuEvent) -> str:
    from app.contrib.golakehavasu import _public_url

    return _public_url(ge)


def _apply_event_merge(db: Session, event_id: str, merge_fields: dict[str, Any] | None) -> bool:
    if not merge_fields:
        return False
    ev = db.get(Event, event_id)
    if ev is None:
        return False
    changed = False
    for key, value in merge_fields.items():
        if key not in _MERGEABLE_EVENT_FIELDS:
            continue
        if getattr(ev, key, None) != value:
            setattr(ev, key, value)
            changed = True
    if changed:
        db.commit()
    return changed


def run_pull(
    start_date: date,
    *,
    dry_run: bool,
    http_client: httpx.Client | None = None,
) -> int:
    """Discover events from the sitemap, reconcile, then insert / merge.

    Returns 0 on success, 1 on fetch error.
    """
    errors = 0
    fetched_urls = 0
    imported = 0
    auto_approved = 0
    auto_approval_failed = 0
    merged_duplicate = 0
    flagged_ambiguous = 0
    skipped_past_or_unparseable = 0

    def body(client: httpx.Client) -> int:
        nonlocal errors, fetched_urls, imported, auto_approved, auto_approval_failed
        nonlocal merged_duplicate, flagged_ambiguous, skipped_past_or_unparseable
        try:
            urls = fetch_sitemap_urls(client=client)
        except Exception as e:
            print(f"error: fetch_sitemap_urls failed: {e}", file=sys.stderr)
            return 1

        fetched_urls = len(urls)

        for url in urls:
            url = (url or "").strip()
            if not url:
                continue
            try:
                ge = fetch_and_parse_event(url, client=client, today=date.today())
            except Exception as e:
                print(f"error: event {url}: {e}", file=sys.stderr)
                errors += 1
                continue
            if ge is None:
                skipped_past_or_unparseable += 1
                continue

            try:
                payload = _to_event_payload(ge)
                with SessionLocal() as db:
                    result = reconcile_event(db, payload, today=date.today())

                    if result.action in ("update", "duplicate"):
                        if not dry_run and result.existing_id:
                            _apply_event_merge(db, result.existing_id, result.merge_fields)
                        merged_duplicate += 1
                        print(
                            f"info: {result.action} -> existing event {result.existing_id} "
                            f"({result.reason}) for {url}"
                        )
                        continue

                    contribution = normalize_to_contribution(ge)
                    if dry_run:
                        imported += 1
                        if result.action == "ambiguous":
                            log_ambiguous_reconcile(result, context=url)
                            flagged_ambiguous += 1
                        continue

                    created = cs.create_contribution(db, contribution)
                    imported += 1

                    if result.action == "ambiguous":
                        # Land pending for human review; do not auto-approve.
                        log_ambiguous_reconcile(result, context=url)
                        flagged_ambiguous += 1
                        continue

                    if should_auto_approve_event(created):
                        try:
                            approve_fields = EventApprovalFields(
                                title=contribution.submission_name,
                                description=(contribution.submission_notes or ""),
                                date=contribution.event_date,
                                end_date=contribution.event_end_date,
                                start_time=contribution.event_time_start,
                                end_time=contribution.event_time_end,
                                location_name=ge.venue_name or "Lake Havasu City",
                                event_url=str(contribution.submission_url or ge.url),
                                source_url=contribution.source_url,
                            )
                            ev = approve_contribution_as_event(
                                db, created.id, approve_fields, list(payload.tags or [])
                            )
                            auto_approved += 1
                            print(
                                f"info: auto-approved golakehavasu contribution "
                                f"{created.id} -> event {ev.id}"
                            )
                        except Exception as e:
                            auto_approval_failed += 1
                            print(
                                f"warning: auto-approval failed for contribution {created.id}: {e}",
                                file=sys.stderr,
                            )
            except Exception as e:
                print(f"error: event {url}: {e}", file=sys.stderr)
                errors += 1

        print("golakehavasu pull complete (sitemap + HTML + event reconciler)")
        print(f"  start_date (CLI, informational): {start_date.isoformat()}")
        print(f"  fetched_urls:                  {fetched_urls}")
        print(f"  imported:                      {imported}")
        print(f"  auto_approved:                 {auto_approved}")
        print(f"  auto_approval_failed:          {auto_approval_failed}")
        print(f"  merged_duplicate:              {merged_duplicate}")
        print(f"  flagged_ambiguous (pending):   {flagged_ambiguous}")
        print(f"  skipped_past_or_unparseable:   {skipped_past_or_unparseable}")
        print(f"  errors:                        {errors}")
        if dry_run:
            print("  (dry run -- no database writes)")
        return 1 if errors else 0

    if http_client is not None:
        return body(http_client)
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        return body(client)
