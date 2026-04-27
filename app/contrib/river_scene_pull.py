"""
Orchestration: RiverScene → contributions queue (Phase 8.10).

``scripts/river_scene_pull.py`` is a thin CLI over :func:`run_pull`.
"""

from __future__ import annotations

import difflib
import re
import sys
from datetime import date

import httpx
from sqlalchemy.orm import Session

from app.contrib.river_scene import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    RiverSceneEvent,
    fetch_and_parse_event,
    fetch_sitemap_urls,
    normalize_to_contribution,
)
from app.contrib.approval_service import approve_contribution_as_event
from app.db import contribution_store as cs
from app.db.database import SessionLocal
from app.db.models import Event
from app.schemas.contribution import EventApprovalFields


def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _find_seed_overlap(db: Session, rse: RiverSceneEvent) -> Event | None:
    """Fuzzy match title + same calendar date on seed events."""
    for ev in db.query(Event).filter(Event.created_by == "seed").all():
        if ev.date != rse.start_date:
            continue
        a = _norm_title(ev.title or "")
        b = _norm_title(rse.title or "")
        if not a or not b:
            continue
        if difflib.SequenceMatcher(None, a, b).ratio() > 0.85:
            return ev
    return None


def _event_url_taken(db: Session, url: str) -> bool:
    n = cs.normalize_submission_url(url)
    if not n:
        return False
    for ev in db.query(Event).all():
        if not ev.event_url:
            continue
        if cs.normalize_submission_url(ev.event_url) == n:
            return True
    return False


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
    skipped_past_or_unparseable = 0
    flagged_seed_overlap = 0
    fetched_urls = 0
    auto_approved = 0
    auto_approval_failed = 0

    def body(client: httpx.Client) -> int:
        nonlocal errors, imported, skipped_duplicate, skipped_past_or_unparseable, flagged_seed_overlap, fetched_urls, auto_approved, auto_approval_failed
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
                norm_url = cs.normalize_submission_url(url)
                if norm_url and cs.has_pending_or_approved_duplicate_url(db, norm_url):
                    skipped_duplicate += 1
                    continue
                if _event_url_taken(db, url):
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

            try:
                payload = normalize_to_contribution(rse)
                url_str = str(payload.submission_url) if payload.submission_url else ""
                with SessionLocal() as db:
                    seed_hit = _find_seed_overlap(db, rse)
                    if seed_hit is not None:
                        prefix = (
                            f"[POSSIBLE DUPLICATE OF SEED EVENT: {seed_hit.title} "
                            f"({seed_hit.date})]\n\n"
                        )
                        notes = payload.submission_notes or ""
                        payload = payload.model_copy(update={"submission_notes": prefix + notes})
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
                                start_time=payload.event_time_start,
                                end_time=payload.event_time_end,
                                location_name=rse.venue_name or "Lake Havasu",
                                event_url=url_str,
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
        print(f"  skipped_past_or_unparseable:   {skipped_past_or_unparseable}")
        print(f"  flagged_seed_overlap:          {flagged_seed_overlap}")
        print(f"  errors:                        {errors}")
        if dry_run:
            print("  (dry run — no database writes)")

        return 1 if errors else 0

    if http_client is not None:
        return body(http_client)
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        return body(client)
