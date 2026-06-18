"""Backfill: repair placeholder/metadata event descriptions, bad click-through
URLs, and glued venue strings on existing live events — using the same shared
guardrails the ingest/approval path now enforces (so new + existing rows agree).

  python scripts/clean_event_descriptions.py                # preview (default, no writes)
  python scripts/clean_event_descriptions.py --dry-run      # explicit preview
  python scripts/clean_event_descriptions.py --enrich       # also re-fetch source pages to recover real text (preview)
  python scripts/clean_event_descriptions.py --enrich --apply   # recover + persist
  python scripts/clean_event_descriptions.py --apply        # persist (clean-only, no network)

What it does per live event:
  * description: collapse metadata-only / placeholder bodies to empty (the event
    detail template then renders the structured sparse-event card). With
    ``--enrich`` it first tries to recover the *real* description from the event's
    own source page (``source_url`` then ``event_url``), rate-limited.
  * event_url: replace an email-as-URL / dead-host / non-http click-through with
    the safe ``/events-ui`` fallback.
  * location_name: fix the glued "…NLake Havasu City" glitch and the
    "No Address Available" tail.

Safe by default: ``--dry-run`` is implied unless ``--apply`` is passed. Follows the
repo rule: dry-run -> show counts -> get approval -> apply.
"""

from __future__ import annotations

import argparse
import sys
import time as _time
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.contrib.event_enrich import enrich_event_records
from app.contrib.event_ingest import _live_music_tags
from app.contrib.event_record import EventRecord
from app.db.database import SessionLocal
from app.db.models import Event
from app.events.description_clean import (
    clean_event_description,
    is_synthetic_placeholder,
    normalize_location_text,
    valid_event_url,
)

_FALLBACK_URL = "https://askhava.com/events-ui"


@dataclass
class Repair:
    new_description: str
    new_event_url: str
    new_location_name: str
    desc_changed: bool
    url_changed: bool
    loc_changed: bool

    @property
    def any_change(self) -> bool:
        return self.desc_changed or self.url_changed or self.loc_changed


def plan_event_repair(
    *,
    title: str | None,
    description: str | None,
    event_url: str | None,
    location_name: str | None,
    start_date: date | None,
) -> Repair:
    """Pure planning step (no DB/network) — easy to unit test."""
    # Description: keep real prose, drop metadata/placeholder/synthesis to "".
    # NOTE: empty string, NOT None — the events.description column is NOT NULL,
    # and the live ingest/approval path also stores "" (the detail template
    # renders the structured sparse-event card for any falsy description).
    if is_synthetic_placeholder(
        description, title=title, location_name=location_name, start_date=start_date
    ):
        new_desc = ""
    else:
        new_desc = clean_event_description(description) or ""
    desc_changed = (description or "").strip() != (new_desc or "")

    # URL: drop email-as-URL / dead host / non-http.
    new_url = valid_event_url(event_url) or _FALLBACK_URL
    url_changed = (event_url or "").strip() != new_url

    # Location: fix glued city + tail.
    norm_loc = normalize_location_text(location_name) or (location_name or "").strip()
    loc_changed = (location_name or "").strip() != norm_loc

    return Repair(
        new_description=new_desc,
        new_event_url=new_url,
        new_location_name=norm_loc,
        desc_changed=desc_changed,
        url_changed=url_changed,
        loc_changed=loc_changed,
    )


def run(*, apply: bool, enrich: bool) -> dict[str, int]:
    counts = {
        "total": 0,
        "desc_cleared": 0,
        "desc_enriched": 0,
        "url_fixed": 0,
        "loc_fixed": 0,
        "time_fixed": 0,
        "tags_fixed": 0,
        "rows_changed": 0,
    }
    midnight = time(0, 0)
    fetch_text = None
    if enrich:
        import httpx

        client = httpx.Client(
            headers={"User-Agent": "havasu-chat/1.0 event-backfill"},
            follow_redirects=True,
            timeout=30.0,
        )

        def fetch_text(u: str) -> str | None:  # noqa: ANN001
            _time.sleep(0.5)
            r = client.get(u)
            return r.text if r.status_code == 200 else None

    with SessionLocal() as db:  # type: Session
        events = db.execute(select(Event).where(Event.status == "live").order_by(Event.id)).scalars().all()
        for ev in events:
            counts["total"] += 1

            # Build a record from the row. With --enrich we re-fetch the source
            # detail page to recover a real description, start time, and venue.
            src_url = valid_event_url(ev.source_url) or valid_event_url(ev.event_url)
            rec = EventRecord(
                source=(ev.source or "backfill"),
                title=ev.title or "",
                start_date=ev.date,
                start_time=ev.start_time,
                end_date=ev.end_date,
                end_time=ev.end_time,
                venue_name=ev.location_name,
                url=src_url,
                description=ev.description or "",
                tags=list(ev.tags or []),
                raw={},
            )
            enriched_desc = False
            if enrich and fetch_text is not None:
                had_desc = bool(clean_event_description(rec.description))
                enrich_event_records([rec], fetch_text=fetch_text, source=rec.source)
                if not had_desc and clean_event_description(rec.description):
                    enriched_desc = True

            # description: prefer enriched prose; else clean; placeholder -> ""
            if is_synthetic_placeholder(
                ev.description, title=ev.title, location_name=ev.location_name, start_date=ev.date
            ):
                base_desc = ""
            else:
                base_desc = clean_event_description(ev.description) or ""
            new_desc = clean_event_description(rec.description) or base_desc
            desc_changed = (ev.description or "").strip() != (new_desc or "")

            # url: drop email-as-URL / dead host / non-http
            new_url = valid_event_url(ev.event_url) or _FALLBACK_URL
            url_changed = (ev.event_url or "").strip() != new_url

            # venue: prefer an enriched real venue; always normalize
            cand_loc = rec.venue_name if (enrich and rec.venue_name) else ev.location_name
            new_loc = normalize_location_text(cand_loc) or (ev.location_name or "").strip()
            loc_changed = (ev.location_name or "").strip() != new_loc

            # time: fill only when ours is missing / midnight (a date-only artifact)
            new_start, new_end, time_changed = ev.start_time, ev.end_time, False
            if (ev.start_time is None or ev.start_time == midnight) and rec.start_time and rec.start_time != midnight:
                new_start, new_end, time_changed = rec.start_time, rec.end_time, True

            # tags: reconcile the machine-managed `music` tag — add it when the
            # event is live music, and remove it when an earlier run added it in
            # error (e.g. a kids "Glow in the Park — All Ages" party with a DJ).
            # Other tags are left untouched.
            rec.venue_name, rec.description = new_loc, new_desc
            existing_tags = list(ev.tags or [])
            should_music = bool(_live_music_tags(rec))
            new_tags = existing_tags[:]
            if should_music and "music" not in new_tags:
                new_tags.append("music")
            elif not should_music and "music" in new_tags:
                new_tags = [t for t in new_tags if t != "music"]
            tags_changed = new_tags != existing_tags

            if not (desc_changed or url_changed or loc_changed or time_changed or tags_changed):
                continue
            if desc_changed:
                counts["desc_enriched" if enriched_desc else "desc_cleared"] += 1
            if url_changed:
                counts["url_fixed"] += 1
            if loc_changed:
                counts["loc_fixed"] += 1
            if time_changed:
                counts["time_fixed"] += 1
            if tags_changed:
                counts["tags_fixed"] += 1
            counts["rows_changed"] += 1

            print(f"--- event {ev.id}  {ev.title!r}")
            if desc_changed:
                print(f"  description -> ({len(new_desc)} chars){' [enriched]' if enriched_desc else ''}")
            if time_changed:
                print(f"  start_time: {ev.start_time} -> {new_start}")
            if loc_changed:
                print(f"  location_name: {ev.location_name!r} -> {new_loc!r}")
            if url_changed:
                print(f"  event_url: {ev.event_url!r} -> {new_url!r}")
            if tags_changed:
                print(f"  tags: {existing_tags} -> {new_tags}")

            if apply:
                ev.description = new_desc or ""
                ev.event_url = new_url
                ev.location_name = new_loc
                ev.start_time = new_start
                ev.end_time = new_end
                ev.tags = new_tags
        if apply:
            db.commit()

    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="persist changes (default: dry-run preview)")
    ap.add_argument("--dry-run", action="store_true", help="explicit preview (default behaviour)")
    ap.add_argument("--enrich", action="store_true", help="re-fetch source pages to recover real descriptions")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run
    counts = run(apply=apply, enrich=args.enrich)
    print("\nclean_event_descriptions complete")
    for k, v in counts.items():
        print(f"  {k:<16} {v}")
    if not apply:
        print("  (dry run -- no database writes; re-run with --apply to persist)")


if __name__ == "__main__":
    main()
