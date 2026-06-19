"""One-time / on-demand loader for the Star Cinemas FREE Summer Kids Movie Series.

The free series is published on a flyer (not in the Veezi showtimes feed), so the
schedule lives in ``SERIES`` below. It's written into the dedicated
``movie_showtimes`` table as FREE showings (``is_free=True``) — NOT the events
pipeline. Idempotent upsert on (source, source_stable_id); re-running updates.

Source: starcinemashavasu.com/deals (2026 "Free Summer Movies & Giveaways" —
Mon-Thu, doors 9:00 AM, showtime 9:30 AM, giveaways before every screening).

Usage:
  python scripts/load_star_cinemas_kids_series.py --dry-run
  python scripts/load_star_cinemas_kids_series.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.movies.store import ShowtimeRecord, upsert_showtimes  # noqa: E402

SOURCE = "star_cinemas_kids_series"
THEATER_SLUG = "star-cinemas"
THEATER_NAME = "Star Cinemas"
INFO_URL = "https://starcinemashavasu.com/deals"
_TMDB = "https://image.tmdb.org/t/p/w500"

# One row per title; each shows Mon-Thu of its week at 9:30 AM. Posters from TMDB.
SHOWTIME = ["9:30"]
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
    {"title": "IF (2024)", "rating": "PG",
     "poster": _TMDB + "/xbKFv4KF3sVYuWKllLlwWDmuZP7.jpg",
     "dates": ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"], "times": SHOWTIME},
    {"title": "Dora and the Lost City of Gold", "rating": "PG",
     "poster": _TMDB + "/xvYCZ740XvngXK0FNeSNVTJJJ5v.jpg",
     "dates": ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"], "times": SHOWTIME},
    {"title": "Teenage Mutant Ninja Turtles: Mutant Mayhem", "rating": "PG",
     "poster": _TMDB + "/gyh0eECE2IqrW8GWl3KoHBfc45j.jpg",
     "dates": ["2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16"], "times": SHOWTIME},
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "film"


def _records() -> list[ShowtimeRecord]:
    out: list[ShowtimeRecord] = []
    for row in SERIES:
        title = (row.get("title") or "").strip()
        if not title:
            continue
        poster = (row.get("poster") or "").strip() or None
        rating = (row.get("rating") or "").strip() or None
        for d in row.get("dates", []):
            day = date.fromisoformat(d)
            for t in row.get("times", []):
                hh, mm = (int(x) for x in t.split(":"))
                sid = f"{day.isoformat()}-{hh:02d}{mm:02d}-{_slug(title)}"
                out.append(
                    ShowtimeRecord(
                        source=SOURCE,
                        source_stable_id=sid,
                        theater_slug=THEATER_SLUG,
                        theater_name=THEATER_NAME,
                        film_title=title,
                        show_date=day,
                        show_time=time(hh, mm),
                        rating=rating,
                        genre="Family",
                        poster_url=poster,
                        booking_url=INFO_URL,
                        is_free=True,
                        tags=["free", "kids", "summer-series"],
                    )
                )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load Star Cinemas free kids series")
    parser.add_argument("--apply", action="store_true", help="write (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    dry_run = not args.apply or args.dry_run

    records = _records()
    if not records:
        print("SERIES is empty -- fill it from the flyer first. Nothing to do.")
        return 0

    if dry_run:
        print(f"DRY RUN: {len(records)} kids-series showings (no writes)")
        return 0

    with SessionLocal() as db:
        counts = upsert_showtimes(db, records)
    print(f"APPLY: created {counts['created']}  updated {counts['updated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
