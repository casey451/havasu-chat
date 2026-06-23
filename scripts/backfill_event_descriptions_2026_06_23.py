"""Backfill missing event descriptions (and fix title-as-venue rows) by
re-fetching each event's source page (2026-06-23).

Casey's calendar has real events that lack a prose description (the Farmers
Market ×27, July-4th Fireworks, the parade, Taste of Havasu, …) — all imported
from riverscenemagazine.com event pages that DO carry a blurb the older import
dropped. This re-fetches each such event's ``source_url`` with the live parser
(:func:`app.contrib.river_scene.fetch_and_parse_event`) and fills:

* ``description`` — when the event currently has none and the source page does;
* ``location_name`` — when the stored venue is the title-as-venue artifact and
  the source page names a real venue.

Prod-DB op — DRY-RUN by default; ``--apply --confirm`` to write (snapshot first).
It makes outbound HTTPS requests to riverscenemagazine.com, so run it where the
scraper's network works (``railway run`` in prod, not a sandbox):

    railway run python scripts/backfill_event_descriptions_2026_06_23.py                    # DRY RUN
    railway run python scripts/backfill_event_descriptions_2026_06_23.py --apply --confirm  # writes
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.river_scene import fetch_and_parse_event  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.description_clean import clean_event_description  # noqa: E402
from app.events.scrapers.base import normalize_event_title  # noqa: E402

# Disable the parser's "skip past-dated pages" guard — we want the description
# regardless of the page's own date semantics.
_NO_PAST_GUARD = date(1900, 1, 1)


def _target() -> str:
    url = DATABASE_URL or ""
    return "..." + url.split("@", 1)[1] if "@" in url else (url or "(unset)")


def _needs_description(ev: Event) -> bool:
    return not (ev.description or "").strip()


def _is_title_as_venue(ev: Event) -> bool:
    loc = (ev.location_name or "").strip()
    return bool(loc) and bool(ev.title) and (
        normalize_event_title(loc) == normalize_event_title(ev.title)
    )


def run(*, apply: bool, confirm: bool) -> int:
    print(f"target: {_target()}")
    with SessionLocal() as db:
        events = (
            db.query(Event)
            .filter(Event.status == "live", Event.date >= date.today())
            .all()
        )
        targets = [e for e in events if _needs_description(e) or _is_title_as_venue(e)]
        print(f"scanned live upcoming events: {len(events)}")
        print(f"events needing description/venue: {len(targets)}\n")

        # Use an explicit certifi CA bundle: the scraper's default client trusts
        # the OS store, which is missing/locked-down in some run environments
        # (the prod cron is fine, a sandbox is not). certifi works in both.
        import certifi
        import httpx

        http_client = httpx.Client(
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            verify=certifi.where(),
            headers={"User-Agent": "AskHavaBot/1.0 (+https://askhava.com)"},
        )

        cache: dict[str, object] = {}
        proposals = []  # (ev, new_desc_or_None, new_venue_or_None)
        for ev in targets:
            src = (getattr(ev, "source_url", None) or "").strip()
            if not src:
                continue
            if src not in cache:
                try:
                    cache[src] = fetch_and_parse_event(
                        src, client=http_client, today=_NO_PAST_GUARD
                    )
                except Exception as exc:  # noqa: BLE001 — log + skip, never crash the batch
                    print(f"  fetch failed {src}: {exc}", file=sys.stderr)
                    cache[src] = None
            rse = cache[src]
            if rse is None:
                continue
            new_desc = None
            if _needs_description(ev):
                d = clean_event_description(getattr(rse, "description_html", "") or "")
                if d.strip():
                    new_desc = d.strip()
            new_venue = None
            if _is_title_as_venue(ev):
                v = (getattr(rse, "venue_name", None) or "").strip()
                if v and normalize_event_title(v) != normalize_event_title(ev.title or ""):
                    new_venue = v
            if new_desc or new_venue:
                proposals.append((ev, new_desc, new_venue))
        http_client.close()

        got_desc = sum(1 for _e, d, _v in proposals if d)
        got_venue = sum(1 for _e, _d, v in proposals if v)
        print(f"proposed: {got_desc} descriptions, {got_venue} venue fixes "
              f"({len(proposals)} events)\n")
        for ev, d, v in proposals[:60]:
            bits = []
            if d:
                bits.append(f"desc={d[:80]!r}")
            if v:
                bits.append(f"venue={v!r}")
            print(f"   {ev.date} {ev.title!r}: {' | '.join(bits)}")

        report = _ROOT / "event_description_backfill_20260623.csv"
        with report.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "date", "title", "new_description", "new_venue", "source_url"])
            for ev, d, v in proposals:
                w.writerow([ev.id, ev.date, ev.title, d or "", v or "",
                            getattr(ev, "source_url", None)])
        print(f"\nproposal CSV: {report}")

        if not apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply --confirm to backfill.")
            return 0
        if not confirm:
            print("\nREFUSING to write without --confirm.")
            return 2

        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
        snap = _ROOT / f"event_description_backfill_undo_{stamp}.csv"
        with snap.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "old_description", "old_location_name"])
            for ev, _d, _v in proposals:
                w.writerow([ev.id, ev.description or "", ev.location_name or ""])
        for ev, d, v in proposals:
            if d:
                ev.description = d
            if v:
                ev.location_name = v
        db.commit()
        print(f"\nAPPLIED. backfilled {got_desc} descriptions + {got_venue} venues. "
              f"undo snapshot: {snap}")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()
    return run(apply=args.apply, confirm=args.confirm)


if __name__ == "__main__":
    raise SystemExit(main())
