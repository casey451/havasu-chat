"""One-time loader: Star Cinemas FREE Summer Kids Movie Series (2026).

This is NOT a recurring scraper. The free kids series is published on a printed
/ Facebook flyer, not in the Veezi showtimes feed (verified 2026-06-19: the live
``sessions`` feed only carries regular priced public shows). So we load it once
from the flyer. Re-run with ``--apply`` after editing ``SERIES`` below; re-runs
are idempotent (the event pipeline dedups on venue+date+time+title).

Facts confirmed from local listings (havasunews / RiverScene / Go Lake Havasu):
  - Venue:   Star Cinemas, 5601 AZ-95, Lake Havasu City
  - When:    summer, Monday-Thursday mornings (historically ~9-10 AM)
  - Cost:    FREE admission
  - Format:  a different kids/family film each week

TODO (Casey): fill SERIES from the 2026 flyer -- one row per title. The exact
weekly titles/dates are only on the flyer image, so they're left blank here on
purpose rather than guessed. Once filled, run:

    python -m scripts.load_star_cinemas_kids_series --dry-run   # show counts
    python -m scripts.load_star_cinemas_kids_series --apply     # write

Usage mirrors scripts/scrape_events.py and reuses its persistence path, so these
showings flow through the same contributions -> auto-approve -> events pipeline
and land on the movies surface with the free/kids tags.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.events.scrapers.base import EventPayload  # noqa: E402
from scripts.scrape_events import _persist_payload  # noqa: E402

SCRAPE_SOURCE = "star_cinemas_kids_series"
VENUE = "Star Cinemas"
# "More info" link for the free series (no per-show booking page — free /
# first-come). We point at the theater's deals page and append a per-showing
# fragment so each event has a UNIQUE url: the contributions pipeline dedups on
# submission_url, so a shared link would collapse the whole series into one row
# (and collide with Star Cinemas' existing provider record).
KIDS_INFO_URL = "https://starcinemashavasu.com/deals"

# One row per title. ``dates``/``times`` are lists so a title shown several
# mornings in a week is easy to express. Source: starcinemashavasu.com/deals
# (2026 "Free Summer Movies & Giveaways" — Mon-Thu, doors 9:00 AM, showtime
# 9:30 AM, giveaways before every screening). All rated PG / family.
SHOWTIME = ["9:30"]
_TMDB = "https://image.tmdb.org/t/p/w500"
SERIES: list[dict] = [
    {"title": "Sonic the Hedgehog 3", "rating": "PG",
     "poster": _TMDB + "/d8Ryb8AunYAuycVKDp5HpdWPKgC.jpg",
     "dates": ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"], "times": SHOWTIME},
    {"title": "Smurfs", "rating": "PG",
     "poster": _TMDB + "/8o6lkhL32xQJeB52IIG1us5BVey.jpg",
     "dates": ["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11"], "times": SHOWTIME},
    {"title": "Spongebob: Search for Squarepants", "rating": "PG",
     "poster": _TMDB + "/xJnOMMsFASxNiFnG7v3TNIQ3ife.jpg",
     "dates": ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"], "times": SHOWTIME},
    {"title": "Clifford the Big Red Dog", "rating": "PG",
     "poster": _TMDB + "/30ULVKdjBcQTsj2aOSThXXZNSxF.jpg",
     "dates": ["2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25"], "times": SHOWTIME},
    {"title": "IF", "rating": "PG",
     "poster": _TMDB + "/xbKFv4KF3sVYuWKllLlwWDmuZP7.jpg",
     "dates": ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"], "times": SHOWTIME},
    {"title": "Dora and the Lost City of Gold", "rating": "PG",
     "poster": _TMDB + "/xvYCZ740XvngXK0FNeSNVTJJJ5v.jpg",
     "dates": ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"], "times": SHOWTIME},
    {"title": "Teenage Mutant Ninja Turtles: Mutant Mayhem", "rating": "PG",
     "poster": _TMDB + "/gyh0eECE2IqrW8GWl3KoHBfc45j.jpg",
     "dates": ["2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16"], "times": SHOWTIME},
]


def _payloads() -> list[EventPayload]:
    out: list[EventPayload] = []
    for row in SERIES:
        title = (row.get("title") or "").strip()
        if not title:
            continue
        rating = (row.get("rating") or "").strip()
        poster = (row.get("poster") or "").strip() or None
        desc = (
            f"{rating} · Free Summer Movie\n\n"
            "Free family movie at Star Cinemas. Doors open 9:00 AM, showtime "
            "9:30 AM, with giveaways before every screening. First come, first served."
        ).strip()
        for d in row.get("dates", []):
            day = date.fromisoformat(d)
            for t in row.get("times", []):
                hh, mm = (int(x) for x in t.split(":"))
                # Unique per showing so the URL-based dedup keeps each one.
                show_url = f"{KIDS_INFO_URL}#{day.isoformat()}-{hh:02d}{mm:02d}"
                out.append(
                    EventPayload(
                        name=title,
                        entity_type="event",
                        source=SCRAPE_SOURCE,
                        start_date=day,
                        start_time=time(hh, mm),
                        venue_name=VENUE,
                        description=desc,
                        event_url=show_url,
                        source_stable_url=show_url,
                        image_url=poster,
                        # "Free" is conveyed in the description; EventPayload has
                        # no cost field, so don't pass one (would TypeError).
                        tags=["movie", "kids", "free", "summer-series", "star-cinemas"],
                        category_slug="movies",
                    )
                )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load Star Cinemas free kids series")
    parser.add_argument("--apply", action="store_true", help="write (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    dry_run = not args.apply or args.dry_run

    payloads = _payloads()
    if not payloads:
        print("SERIES is empty -- fill it from the 2026 flyer first. Nothing to do.")
        return 0

    print(f"{'DRY RUN' if dry_run else 'APPLY'}: {len(payloads)} kids-series showings")
    counts: dict[str, int] = {}
    for p in payloads:
        with SessionLocal() as db:
            action = _persist_payload(db, p, scrape_source=SCRAPE_SOURCE, dry_run=dry_run)
        counts[action] = counts.get(action, 0) + 1
    for action, n in sorted(counts.items()):
        print(f"  {action}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
