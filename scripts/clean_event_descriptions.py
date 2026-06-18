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
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

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
    new_description: str | None
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
    # Description: keep real prose, drop metadata/placeholder/synthesis to None.
    if is_synthetic_placeholder(
        description, title=title, location_name=location_name, start_date=start_date
    ):
        new_desc = None
    else:
        new_desc = clean_event_description(description) or None
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


def _recover_description(ev: Event, fetch_text) -> str:
    """Try to recover real prose from the event's own source page."""
    from app.contrib.event_enrich import description_from_detail_html

    for url in (ev.source_url, ev.event_url):
        clean = valid_event_url(url)
        if not clean:
            continue
        try:
            html = fetch_text(clean)
        except Exception:  # noqa: BLE001
            continue
        if html:
            better = description_from_detail_html(html)
            if better:
                return better
    return ""


def run(*, apply: bool, enrich: bool) -> dict[str, int]:
    counts = {
        "total": 0,
        "desc_cleared": 0,
        "desc_enriched": 0,
        "url_fixed": 0,
        "loc_fixed": 0,
        "rows_changed": 0,
    }
    fetch_text = None
    if enrich:
        import httpx

        client = httpx.Client(
            headers={"User-Agent": "havasu-chat/1.0 description-backfill"},
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
            plan = plan_event_repair(
                title=ev.title,
                description=ev.description,
                event_url=ev.event_url,
                location_name=ev.location_name,
                start_date=ev.date,
            )
            new_desc = plan.new_description
            enriched = False
            if new_desc is None and enrich and fetch_text is not None:
                recovered = _recover_description(ev, fetch_text)
                if recovered:
                    new_desc = recovered
                    enriched = True

            changed = plan.any_change or enriched
            if not changed:
                continue

            if plan.desc_changed or enriched:
                counts["desc_enriched" if enriched else "desc_cleared"] += 1
            if plan.url_changed:
                counts["url_fixed"] += 1
            if plan.loc_changed:
                counts["loc_fixed"] += 1
            counts["rows_changed"] += 1

            print(f"--- event {ev.id}  {ev.title!r}")
            if plan.desc_changed or enriched:
                tag = "enriched" if enriched else "cleared"
                print(f"  description ({tag}): {(ev.description or '')[:90]!r} -> {(new_desc or '')[:90]!r}")
            if plan.url_changed:
                print(f"  event_url: {ev.event_url!r} -> {plan.new_event_url!r}")
            if plan.loc_changed:
                print(f"  location_name: {ev.location_name!r} -> {plan.new_location_name!r}")

            if apply:
                ev.description = new_desc
                ev.event_url = plan.new_event_url
                ev.location_name = plan.new_location_name
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
