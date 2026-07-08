"""Scrape Movies Havasu showtimes into the ``movie_showtimes`` table.

Movies Havasu (Webedia/Gatsby site) has NO plain-HTTP showtimes feed — the
showtimes only exist in the JS-rendered page — so this uses Playwright to render
the site and read the booking links. It runs ONLY in CI (the
movies-havasu-showtimes GitHub Action installs Playwright + Chromium); the
Railway web app never imports Playwright and stays browser-free.

Hybrid for robustness: Playwright reads only the volatile bit (per-date booking
links grouped by film card), while film metadata (title/rating/runtime/genre/
poster) comes from the theater's stable boxoffice JSON API, keyed by the movie id
in each card's /movies/<id>-... link. Booking ``perfcode`` is globally unique per
showtime, so it's the idempotency key (source_stable_id).

Usage:
  python scripts/scrape_movies_havasu.py --dry-run
  python scripts/scrape_movies_havasu.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

import httpx  # noqa: E402

from app.core.timezone import now_lake_havasu  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.movies.havasu_parse import parse_clock_time, resolve_strip_dates  # noqa: E402
from app.movies.store import (  # noqa: E402
    ShowtimeRecord,
    cross_check_autocorrected,
    prune_past,
    showtime_record_is_suspect,
    upsert_showtimes,
)

SITE = "https://www.movieshavasu.com"
SOURCE = "movies_havasu"
THEATER_SLUG = "movies-havasu"
THEATER_NAME = "Movies Havasu"

# Day-strip buttons read like "Fri19", "Sat20", ... (weekday + day-of-month).
_DAY_BTN_JS = (
    "() => [...document.querySelectorAll('button')]"
    ".map(b => (b.textContent||'').trim())"
    ".filter(t => /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\\d{1,2}$/.test(t))"
)

# Click the i-th day-strip button (re-query each time; the grid re-renders).
_CLICK_DAY_JS = (
    "(i) => { const bs=[...document.querySelectorAll('button')]"
    ".filter(b => /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\\d{1,2}$/.test((b.textContent||'').trim()));"
    " if (bs[i]) bs[i].click(); }"
)

# For the currently-selected date: group booking links under their film card
# (the nearest ancestor that also holds a /movies/<id> link). Avoids the site's
# hashed CSS classes entirely.
_EXTRACT_JS = r"""
() => {
  const cards = new Map();
  for (const a of document.querySelectorAll('a[href*="perfcode"]')) {
    let host = a;
    for (let i = 0; i < 10 && host; i++) {
      host = host.parentElement;
      if (host && host.querySelector('a[href^="/movies/"]')) break;
    }
    if (!host) continue;
    const ml = host.querySelector('a[href^="/movies/"]');
    const m = (ml.getAttribute('href') || '').match(/\/movies\/([^/-]+)/);
    if (!m) continue;
    const id = m[1];
    if (!cards.has(id)) cards.set(id, { id: id, times: [] });
    const pm = a.href.match(/perfcode=(\d+)/);
    cards.get(id).times.push({
      label: (a.textContent || '').trim(),
      url: a.href,
      perfcode: pm ? pm[1] : null,
    });
  }
  return [...cards.values()];
}
"""


def _fetch_metadata(movie_ids: list[str]) -> dict[str, dict]:
    """Title/rating/runtime/genre/poster per movie id, from the boxoffice API."""
    if not movie_ids:
        return {}
    qs = "&".join(f"ids={mid}" for mid in movie_ids)
    url = f"{SITE}/api/gatsby-source-boxofficeapi/movies?basic=false&castingLimit=1&{qs}"
    headers = {"User-Agent": "Ask Hava/0.1 (movie showtimes)", "Accept": "application/json"}
    with httpx.Client(timeout=60.0, headers=headers, follow_redirects=True) as c:
        data = c.get(url).json()
    out: dict[str, dict] = {}
    for m in data if isinstance(data, list) else []:
        mid = str(m.get("id") or "")
        if mid:
            out[mid] = m
    return out


def _records_from_pages(*, today: date) -> list[ShowtimeRecord]:
    from playwright.sync_api import sync_playwright

    by_perfcode: dict[str, tuple[str, date, object, str]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent="Ask Hava/0.1 (movie showtimes)")
            page.goto(SITE, wait_until="networkidle", timeout=90_000)
            page.wait_for_selector('a[href*="perfcode"]', timeout=30_000)
            labels = page.evaluate(_DAY_BTN_JS)
            dates = resolve_strip_dates(list(labels), today=today)
            for idx, show_date in enumerate(dates):
                page.evaluate(_CLICK_DAY_JS, idx)
                page.wait_for_timeout(800)
                cards = page.evaluate(_EXTRACT_JS)
                for card in cards:
                    mid = str(card.get("id") or "")
                    for t in card.get("times", []):
                        perfcode = t.get("perfcode")
                        tm = parse_clock_time(t.get("label"))
                        if not perfcode or tm is None or not mid:
                            continue
                        by_perfcode[perfcode] = (mid, show_date, tm, t.get("url") or "")
        finally:
            browser.close()

    meta = _fetch_metadata(sorted({mid for mid, *_ in by_perfcode.values()}))
    records: list[ShowtimeRecord] = []
    for perfcode, (mid, show_date, tm, url) in by_perfcode.items():
        m = meta.get(mid, {})
        runtime_s = m.get("runtime")
        runtime_min = (
            int(runtime_s) // 60 if isinstance(runtime_s, (int, float)) and runtime_s else None
        )
        poster = m.get("poster")
        records.append(
            ShowtimeRecord(
                source=SOURCE,
                source_stable_id=perfcode,
                theater_slug=THEATER_SLUG,
                theater_name=THEATER_NAME,
                film_title=(m.get("title") or "").strip() or f"Movie {mid}",
                show_date=show_date,
                show_time=tm,  # type: ignore[arg-type]
                rating=(m.get("certificate") or "").strip() or None,
                genre=(m.get("genres") or "").strip() or None,
                runtime_minutes=runtime_min,
                poster_url=poster if isinstance(poster, str) and poster else None,
                booking_url=url or None,
            )
        )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape Movies Havasu showtimes")
    parser.add_argument("--dry-run", action="store_true", help="render only; no DB writes")
    parser.add_argument("--no-prune", action="store_true", help="skip pruning past showings")
    args = parser.parse_args(argv)

    today = now_lake_havasu().date()
    records = _records_from_pages(today=today)
    films = {r.film_title for r in records}
    dates = sorted({r.show_date.isoformat() for r in records})
    span = f"{dates[0]}..{dates[-1]}" if dates else "(none)"
    print(f"scraped {len(records)} showtimes, {len(films)} films, dates {span}")

    # Surface implausibly-early showtimes (before 9 AM — almost always a PM time
    # the source listed as AM). Movies Havasu is an AUTO_CORRECT source, so
    # upsert_showtimes flips these +12h and tags them ``auto_corrected`` (its
    # backend systematically mislabels PM matinees as AM — the booking system has
    # the same flip). Reporting them here lets a --dry-run see exactly what will be
    # corrected, no DB writes.
    suspect = [r for r in records if showtime_record_is_suspect(r)]
    if suspect:
        print(f"AUTO-CORRECT: {len(suspect)} implausible <9AM showtime(s) will flip +12h:")
        for r in sorted(suspect, key=lambda x: (x.show_date, x.show_time, x.film_title)):
            fixed = time((r.show_time.hour + 12) % 24, r.show_time.minute)
            print(f"  {r.show_date.isoformat()} {r.show_time.isoformat()} -> {fixed.isoformat()}  {r.film_title}  {r.booking_url or ''}")

    if args.dry_run:
        print("DRY RUN: no writes")
        return 0

    with SessionLocal() as db:
        counts = upsert_showtimes(db, records)
        pruned = 0 if args.no_prune else prune_past(db)
        # Free cross-check (nightly canary output): flag any auto-corrected showtime
        # whose corrected time is wildly off Star Cinemas' pattern for the same film.
        canary_flags = cross_check_autocorrected(db)
    print(
        f"created: {counts['created']}  updated: {counts['updated']}  "
        f"auto_corrected: {counts['auto_corrected']}  quarantined: {counts['quarantined']}  "
        f"pruned_past: {pruned}"
    )
    for flag in canary_flags:
        print(f"CANARY: {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
