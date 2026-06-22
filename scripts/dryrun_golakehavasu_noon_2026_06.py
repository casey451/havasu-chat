"""P1 cleanup (a-twin) — existing golakehavasu fabricated-noon rows -> "Time TBD".

Sibling of ``dryrun_river_scene_noon_2026_06.py`` for the ``go_lake_havasu``
source. The golakehavasu parser fix (PR #483) stops *new* fabricated-noon rows;
this finds the rows the old parser already wrote to prod and classifies them by
the same source-verified method: re-fetch each event's golakehavasu page
(``source_url``, ``today=event.date`` to bypass the past-date skip) and ask
whether the page actually lists a time.

  * ``fabricated``  — re-fetch parses but finds no time -> would become "Time TBD"
                      (sentinel ``start_time=00:00`` + ``end_time=NULL``; the
                      column is NOT NULL). Event stays ``status='live'``.
  * ``legit_noon``  — the page lists a 12:00 start. KEEP.
  * ``stale_noon``  — the page lists a real non-noon time. FLAG, not auto-fixed.
  * ``unverified``  — page unreachable. LEFT untouched.

**Dry-run is the default — no DB writes.** ``--apply`` is gated and writes a
timestamped undo snapshot first.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\dryrun_golakehavasu_noon_2026_06.py           # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\dryrun_golakehavasu_noon_2026_06.py --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_REPORT_PATH = _ROOT / "golakehavasu_noon_candidates.csv"

NOON = time(12, 0, 0)
TBD_START = time(0, 0, 0)  # is_time_tbd sentinel (start 00:00 + end NULL)


def classify_noon(refetch_ok: bool, refetched_start: time | None) -> str:
    """Pure classifier from the re-fetch outcome (same contract as cleanup-a)."""
    if not refetch_ok:
        return "unverified"
    if refetched_start is None:
        return "fabricated"
    if refetched_start == NOON:
        return "legit_noon"
    return "stale_noon"


@dataclass(frozen=True)
class NoonRow:
    id: str
    date: date
    title: str
    source_url: str
    end_time: time | None


def _load_noon_rows() -> list[NoonRow]:
    from app.db.database import SessionLocal
    from app.db.models import Event

    out: list[NoonRow] = []
    with SessionLocal() as session:
        rows = (
            session.query(Event)
            .filter(
                Event.status == "live",
                Event.source == "go_lake_havasu",
                Event.start_time == NOON,
            )
            .all()
        )
        for e in rows:
            out.append(
                NoonRow(id=e.id, date=e.date, title=e.title, source_url=e.source_url or "", end_time=e.end_time)
            )
    return out


def _build_verified_client():
    import certifi
    import httpx

    from app.contrib.golakehavasu import EVENT_PAGE_HTTP_TIMEOUT, _headers

    return httpx.Client(
        timeout=EVENT_PAGE_HTTP_TIMEOUT, headers=_headers(), follow_redirects=True, verify=certifi.where()
    )


def _refetch_start_time(client, url: str, on_date: date) -> tuple[bool, time | None]:
    from app.contrib.golakehavasu import fetch_and_parse_event

    try:
        ev = fetch_and_parse_event(url, client=client, today=on_date)
    except Exception:
        return (False, None)
    if ev is None:
        return (False, None)
    return (True, ev.start_time)


def run(*, apply: bool = False) -> tuple[Counter, list[tuple[NoonRow, str, time | None]]]:
    rows = _load_noon_rows()
    counts: Counter = Counter()
    counts["scanned"] = len(rows)
    cache: dict[str, tuple[bool, time | None]] = {}
    results: list[tuple[NoonRow, str, time | None]] = []

    with _build_verified_client() as client:
        for r in rows:
            if not r.source_url:
                ok, ft = (False, None)
            elif r.source_url in cache:
                ok, ft = cache[r.source_url]
            else:
                ok, ft = _refetch_start_time(client, r.source_url, r.date)
                cache[r.source_url] = (ok, ft)
            verdict = classify_noon(ok, ft)
            counts[verdict] += 1
            results.append((r, verdict, ft))

    fabricated = [r for (r, v, _ft) in results if v == "fabricated"]
    if apply and fabricated:
        from app.db.database import SessionLocal
        from app.db.models import Event

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _ROOT / f"golakehavasu_noon_undo_{stamp}.csv"
        ids = {r.id for r in fabricated}
        with SessionLocal() as session:
            live = list(session.query(Event).filter(Event.id.in_(ids)))
            with snap.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["id", "old_start_time", "old_end_time"])
                for ev in live:
                    w.writerow([ev.id, ev.start_time, ev.end_time])
            for ev in live:
                ev.start_time = TBD_START
                ev.end_time = None
            session.commit()
        print(f"  undo snapshot written: {snap}")

    with _REPORT_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["classification", "id", "date", "title", "source_url", "refetched_start_time", "db_end_time"])
        for r, v, ft in sorted(results, key=lambda t: (t[1], t[0].date)):
            w.writerow([v, r.id, r.date, r.title, r.source_url, ft if ft else "", r.end_time or ""])
    return counts, results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (omit = dry-run).")
    args = parser.parse_args()

    counts, results = run(apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN (no DB writes)"
    print(f"\ngolakehavasu fabricated-noon cleanup -- {mode}")
    print(f"  go_lake_havasu noon rows scanned: {counts['scanned']}")
    print(f"    fabricated (-> Time TBD):    {counts['fabricated']}")
    print(f"    legit_noon (keep):           {counts['legit_noon']}")
    print(f"    stale_noon (flag, separate): {counts['stale_noon']}")
    print(f"    unverified (page gone/fail): {counts['unverified']}")
    print(f"  candidate CSV: {_REPORT_PATH}")
    for label, key in (("Would convert to 'Time TBD'", "fabricated"), ("FLAGGED stale_noon", "stale_noon"), ("unverified", "unverified")):
        sel = [(r, ft) for (r, v, ft) in results if v == key]
        if sel:
            print(f"\n  {label} -- {len(sel)}:")
            for r, ft in sorted(sel, key=lambda t: t[0].date):
                extra = f" | source says {ft}" if key == "stale_noon" else ""
                print(f"    {r.id[:8]} | {r.date} | {r.title[:55]}{extra}")
    if not args.apply and counts["fabricated"]:
        print("\n  Review, then re-run with --apply to write (prod-data gate; undo snapshot saved first).")


if __name__ == "__main__":
    main()
