"""
Orchestration: RiverScene -> contributions queue (Phase 8.10).

``scripts/river_scene_pull.py`` is a thin CLI over :func:`run_pull`.
"""

from __future__ import annotations

import sys
from datetime import date

import httpx

from app.contrib.approval_service import approve_contribution_as_event
from app.contrib.event_reconciler import reconcile_event
from app.contrib.river_scene import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    RiverSceneEvent,
    _submission_public_url,
    fetch_and_parse_event,
    fetch_sitemap_urls,
    normalize_to_contribution,
)
from app.db import contribution_store as cs
from app.db.database import SessionLocal
from app.db.models import Event
from app.events.scrapers.base import EventPayload
from app.schemas.contribution import EventApprovalFields

# Existing-event sources that are NOT treated as a cross-source duplicate of a
# river_scene import: river_scene's own rows and seed rows (seed overlaps are
# flagged for review when reconcile_event returns duplicate on a seed row).
_RIVER_SCENE_OWN_SOURCES = frozenset({"river_scene", "river_scene_import"})


def _river_scene_event_payload(rse: RiverSceneEvent) -> EventPayload:
    """Build a shared EventPayload from a parsed RiverScene event."""
    return EventPayload(
        name=rse.title,
        entity_type="event",
        source="river_scene",
        start_date=rse.start_date,
        end_date=(rse.end_date if rse.end_date and rse.end_date > rse.start_date else None),
        start_time=rse.start_time,
        end_time=(rse.end_time if rse.end_time != rse.start_time else None),
        venue_name=rse.venue_name,
        address=rse.venue_address,
        description=rse.description_html or "",
        event_url=_submission_public_url(rse),
        source_stable_url=rse.url,
        tags=list(rse.category_slugs or []),
    )


def _prefetch_reconcile_payload(url: str) -> EventPayload:
    """Minimal payload so reconcile_event can check source_url before HTML fetch."""
    return EventPayload(
        name=".",
        entity_type="event",
        source="river_scene",
        start_date=date.today(),
        source_stable_url=url,
    )


def _is_cross_source_duplicate(matched: Event | None) -> bool:
    if matched is None:
        return False
    return (
        (matched.created_by or "") != "seed"
        and (matched.source or "") not in _RIVER_SCENE_OWN_SOURCES
    )


def _seed_overlap_note(matched: Event, notes: str | None) -> str:
    prefix = (
        f"[POSSIBLE DUPLICATE OF SEED EVENT: {matched.title} "
        f"({matched.date})]\n\n"
    )
    return prefix + (notes or "")


def run_pull(
    start_date: date,
    *,
    dry_run: bool,
    http_client: httpx.Client | None = None,
) -> int:
    """
    Discover event URLs from the site sitemap, dedupe before fetching HTML,
    then insert contributions (or dry-run). Returns 0 on success, 1 on fetch error.
    """
    errors = 0
    imported = 0
    skipped_duplicate = 0
    skipped_cross_source = 0
    skipped_past_or_unparseable = 0
    flagged_seed_overlap = 0
    fetched_urls = 0
    auto_approved = 0
    auto_approval_failed = 0

    def body(client: httpx.Client) -> int:
        nonlocal errors, imported, skipped_duplicate, skipped_cross_source, skipped_past_or_unparseable, flagged_seed_overlap, fetched_urls, auto_approved, auto_approval_failed
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
            with SessionLocal() as db:
                pre = reconcile_event(db, _prefetch_reconcile_payload(url))
                if pre.action == "update" and pre.reason == "source_url exact match":
                    skipped_duplicate += 1
                    continue

            try:
                rse = fetch_and_parse_event(url, client=client, today=date.today())
            except Exception as e:
                print(f"error: event {url}: {e}", file=sys.stderr)
                errors += 1
                continue

            if rse is None:
                skipped_past_or_unparseable += 1
                continue

            event_payload = _river_scene_event_payload(rse)
            try:
                payload = normalize_to_contribution(rse)
                url_str = str(payload.submission_url) if payload.submission_url else ""
                with SessionLocal() as db:
                    rec = reconcile_event(db, event_payload)
                    if rec.action == "update":
                        skipped_duplicate += 1
                        continue
                    if rec.action == "duplicate" and rec.existing_id:
                        matched = db.get(Event, rec.existing_id)
                        if _is_cross_source_duplicate(matched):
                            skipped_cross_source += 1
                            print(
                                f"info: skip cross-source duplicate of event "
                                f"{rec.existing_id} ({rec.reason}) for {url}"
                            )
                            continue
                        if matched is not None and (matched.created_by or "") == "seed":
                            notes = payload.submission_notes or ""
                            payload = payload.model_copy(
                                update={"submission_notes": _seed_overlap_note(matched, notes)}
                            )
                            flagged_seed_overlap += 1
                    if dry_run:
                        imported += 1
                        continue
                    created = cs.create_contribution(db, payload)
                    imported += 1
                    if payload.source == "river_scene_import":
                        try:
                            approve_fields = EventApprovalFields(
                                title=payload.submission_name,
                                description=(payload.submission_notes or ""),
                                date=payload.event_date,
                                end_date=payload.event_end_date,
                                start_time=payload.event_time_start,
                                end_time=payload.event_time_end,
                                location_name=rse.venue_name or "Lake Havasu",
                                event_url=url_str,
                                source_url=payload.source_url,
                            )
                            ev = approve_contribution_as_event(db, created.id, approve_fields, list(rse.category_slugs or []))
                            auto_approved += 1
                            print(
                                f"info: auto-approved river scene contribution {created.id} -> event {ev.id}"
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

        print("River Scene pull complete (sitemap + HTML)")
        print(f"  start_date (CLI, informational): {start_date.isoformat()}")
        print(f"  fetched_urls:                  {fetched_urls}")
        print(f"  imported:                      {imported}")
        print(f"  auto_approved:                 {auto_approved}")
        print(f"  auto_approval_failed:          {auto_approval_failed}")
        print(f"  skipped_duplicate:             {skipped_duplicate}")
        print(f"  skipped_cross_source:          {skipped_cross_source}")
        print(f"  skipped_past_or_unparseable:   {skipped_past_or_unparseable}")
        print(f"  flagged_seed_overlap:          {flagged_seed_overlap}")
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
