"""
Backfill ``event_url``, ``description``, and ``source_url`` on River Scene–imported
events using current ingestion logic (re-fetch article HTML).

  python scripts/backfill_river_scene_urls.py              # preview (default)
  python scripts/backfill_river_scene_urls.py --dry-run    # explicit preview
  python scripts/backfill_river_scene_urls.py --apply      # persist updates
  python scripts/backfill_river_scene_urls.py --cleanup-only           # strip legacy prefix only
  python scripts/backfill_river_scene_urls.py --cleanup-only --dry-run
  python scripts/backfill_river_scene_urls.py --cleanup-only --apply

Preview prints field diffs; ``--apply`` commits per updated row. Rate-limited (0.5s)
between HTTP fetches in scrape mode.

Counter partition (rescrape): ``total == no_article_url + skipped_fetch + would_change + no_change``.
``no_organizer_url_available`` counts rows whose parsed public URL equals the article URL only
(orthogonal to ``would_change`` / ``no_change``).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.tier2_formatter import _strip_legacy_fallback
from app.contrib.river_scene import (
    EVENT_PAGE_HTTP_TIMEOUT,
    USER_AGENT,
    _article_url_with_scheme,
    fetch_and_parse_event,
    normalize_to_contribution,
)
from app.db.contribution_store import normalize_submission_url
from app.db.database import SessionLocal
from app.db.models import Contribution, Event

_RS_HOST = "riverscenemagazine.com"
_FETCH_AS_OF = date.min  # backfill must parse past-dated pages


def _iter_river_scene_events(db: Session) -> Iterator[Event]:
    stmt = select(Event).where(Event.source == "river_scene_import").order_by(Event.id)
    yield from db.execute(stmt).scalars().all()


def _contribution_for_event(db: Session, event_id: str) -> Contribution | None:
    return (
        db.execute(
            select(Contribution)
            .where(Contribution.created_event_id == event_id)
            .order_by(Contribution.id)
            .limit(1)
        )
        .scalars()
        .one_or_none()
    )


def _pick_article_fetch_url(ev: Event, c: Contribution | None) -> str | None:
    """Prefer a riverscenemagazine article URL; fall back to first candidate."""
    candidates: list[str] = []
    if c is not None and (c.submission_url or "").strip():
        candidates.append(c.submission_url.strip())
    if (ev.event_url or "").strip():
        candidates.append(ev.event_url.strip())
    if (ev.source_url or "").strip():
        candidates.append(ev.source_url.strip())
    for u in candidates:
        if _RS_HOST in u.lower():
            return u
    return candidates[0] if candidates else None


def _norm_pair(source_url: str | None, submission_url: str | None) -> tuple[str, str]:
    return (
        normalize_submission_url(source_url) or "",
        normalize_submission_url(submission_url) or "",
    )


def _payload_targets(payload) -> tuple[str, str, str]:
    su = payload.submission_url
    event_url = str(su).strip() if su is not None else ""
    desc = (payload.submission_notes or "").strip()
    src_key = normalize_submission_url(payload.source_url) or ""
    return event_url, desc, src_key


def _proposed_event_url_is_article_fallback_only(rse, event_url: str) -> bool:
    """True when normalized proposed ``event_url`` is only the article URL (no Website/Facebook distinct URL)."""
    art = normalize_submission_url(_article_url_with_scheme(rse.url)) or ""
    pub = normalize_submission_url(event_url) or ""
    return pub == art


def _event_needs_update(ev: Event, event_url: str, description: str, src_key: str) -> bool:
    cur_src, cur_ev_u = _norm_pair(ev.source_url, ev.event_url)
    new_src, new_ev_u = _norm_pair(src_key if src_key else None, event_url if event_url else None)
    if (ev.description or "").strip() != description:
        return True
    if cur_ev_u != new_ev_u:
        return True
    if cur_src != new_src:
        return True
    return False


def _print_diff(ev_id: str, ev: Event, event_url: str, description: str, src_key: str) -> None:
    print(f"--- event {ev_id}")
    if (ev.event_url or "").strip() != event_url:
        print(f"  event_url:     {ev.event_url!r}")
        print(f"            ->   {event_url!r}")
    if (ev.description or "").strip() != description:
        print(f"  description:   (len {len(ev.description)}) -> (len {len(description)})")
        print(f"            was: {ev.description[:200]!r}...")
        print(f"            now: {description[:200]!r}...")
    print(f"  source_url:    {ev.source_url!r}")
    print(f"            ->   {src_key!r}")


def run_rescrape(*, apply: bool) -> tuple[int, int, int, int, int, int, int]:
    """
    Returns ``(total, would_change, no_change, no_organizer_url_available, applied,
    skipped_fetch, no_article_url)``.
    """
    total = would_change = no_change = no_org = applied = skipped_fetch = no_url = 0
    client = httpx.Client(
        timeout=EVENT_PAGE_HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
    try:
        with SessionLocal() as db:
            events = list(_iter_river_scene_events(db))
            n = len(events)
            for i, ev in enumerate(events):
                total += 1
                c = _contribution_for_event(db, ev.id)
                article = _pick_article_fetch_url(ev, c)
                if not article:
                    no_url += 1
                    print(
                        f"warning: event {ev.id}: no URL candidate for re-fetch — skip",
                        file=sys.stderr,
                    )
                    continue

                rse = None
                try:
                    rse = fetch_and_parse_event(article, client=client, today=_FETCH_AS_OF)
                except Exception as e:
                    skipped_fetch += 1
                    logging.exception("event %s: fetch failed", ev.id)
                    print(f"warning: event {ev.id}: fetch error: {e}", file=sys.stderr)
                    if i < n - 1:
                        time.sleep(0.5)
                    continue

                if rse is None:
                    skipped_fetch += 1
                    print(
                        f"warning: event {ev.id}: could not parse article {article!r} — skip",
                        file=sys.stderr,
                    )
                    if i < n - 1:
                        time.sleep(0.5)
                    continue

                payload = normalize_to_contribution(rse)
                event_url, description, src_key = _payload_targets(payload)

                if _proposed_event_url_is_article_fallback_only(rse, event_url):
                    no_org += 1

                if not _event_needs_update(ev, event_url, description, src_key):
                    no_change += 1
                    if i < n - 1:
                        time.sleep(0.5)
                    continue

                would_change += 1
                _print_diff(ev.id, ev, event_url, description, src_key)

                cur_c_ev_u = normalize_submission_url(c.submission_url) if c else ""
                cur_c_src = normalize_submission_url(c.source_url) if c else ""
                new_c_ev_u = normalize_submission_url(event_url) or ""
                new_c_src = src_key
                if c is not None and (cur_c_ev_u != new_c_ev_u or cur_c_src != new_c_src):
                    print(
                        f"  contribution {c.id}: submission_url / source_url "
                        f"would align with event"
                    )

                if apply:
                    ev.event_url = event_url
                    ev.description = description
                    ev.source_url = src_key if src_key else None
                    db.add(ev)
                    if c is not None:
                        c.submission_url = event_url or None
                        c.source_url = src_key if src_key else None
                        db.add(c)
                    db.commit()
                    applied += 1
                    print(f"info: applied update for event {ev.id}")

                if i < n - 1:
                    time.sleep(0.5)
    finally:
        client.close()

    print("River Scene URL backfill (rescrape) complete")
    print(f"  total:                         {total}")
    print(f"  would_change:                  {would_change}")
    print(f"  no_change:                     {no_change}")
    print(f"  no_organizer_url_available:    {no_org}")
    print(f"  applied:                       {applied}")
    print(f"  skipped_fetch:                 {skipped_fetch}")
    print(f"  no_article_url:                {no_url}")
    if apply:
        assert applied == would_change, f"applied ({applied}) != would_change ({would_change})"
    else:
        assert applied == 0, f"dry-run must not persist rows (applied={applied})"
    if total != no_url + skipped_fetch + would_change + no_change:
        raise RuntimeError(
            "counter partition broken: total != no_article_url + skipped_fetch + would_change + no_change"
        )
    return total, would_change, no_change, no_org, applied, skipped_fetch, no_url


def run_cleanup_only(*, apply: bool) -> tuple[int, int, int]:
    """Strip legacy description prefix only; no HTTP."""
    total = would_change = applied = 0
    with SessionLocal() as db:
        for ev in _iter_river_scene_events(db):
            total += 1
            new_desc = _strip_legacy_fallback(ev.description)
            if new_desc == (ev.description or "").strip():
                continue
            would_change += 1
            print(f"--- event {ev.id} description cleanup")
            print(f"  was: {ev.description[:240]!r}...")
            print(f"  now: {new_desc[:240]!r}...")
            print(f"  source_url:    {ev.source_url!r}")
            print(f"            ->   {ev.source_url!r}")
            if apply:
                ev.description = new_desc
                db.add(ev)
                db.commit()
                applied += 1
                print(f"info: applied description cleanup for event {ev.id}")

    print("River Scene cleanup-only (description prefix) complete")
    print(f"  total:        {total}")
    print(f"  would_change: {would_change}")
    print(f"  applied:      {applied}")
    if apply:
        assert applied == would_change, f"applied ({applied}) != would_change ({would_change})"
    else:
        assert applied == 0, f"cleanup preview must not persist rows (applied={applied})"
    return total, would_change, applied


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing (same as omitting mode flags).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Persist updates to the database.",
    )
    p.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Do not fetch; strip legacy River Scene description prefix only.",
    )
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    if args.cleanup_only:
        run_cleanup_only(apply=bool(args.apply))
    else:
        run_rescrape(apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
