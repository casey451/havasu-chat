"""P1 cleanup (a) — existing River Scene fabricated-noon rows -> "Time TBD".

PR #481 stopped the River Scene parser from fabricating a 12:00 PM start when a
source page has no Time row. This script handles the rows that the OLD parser
already wrote to prod: live ``river_scene_import`` events stamped ``start_time``
12:00:00.

**Precision is the whole point** (Casey: "do NOT touch legitimately-noon
events"). A noon row in the DB is ambiguous on its own — it might be a real noon
event. So this script re-fetches each event's RiverScene *article* (the
``source_url``) and asks the only authority that matters: does the source page
actually list a Time?

  * ``fabricated``  — re-fetch parses cleanly but finds NO Time row (the old
                      noon was invented). These are the conversion candidates.
  * ``legit_noon``  — the source page lists a 12:00 start. KEEP untouched.
  * ``stale_noon``  — the source lists a real *non-noon* time but the DB shows
                      12:00. A different bug (wrong stored time, not a fabricated
                      placeholder). FLAGGED, never auto-converted here.
  * ``unverified``  — the article 404s / won't parse. LISTED, never touched.

``Event.start_time`` is ``NOT NULL`` in the schema, so "Time TBD" is stored as
the sentinel the time-label contract recognizes (``app/events/time_labels.py``):
``start_time = 00:00`` + ``end_time = NULL``. The event stays ``status='live'``;
only its time becomes "Time TBD". A timestamped snapshot of the old times is
written before any mutation, so the change is fully reversible.

**Dry-run is the default — no DB writes, no STOP skipped.** Mutating prod follows
repo discipline: re-fetch + classify + print counts + write the candidate CSV;
mutate only under ``--apply`` (gated on Casey's approval of the dry-run counts).

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\dryrun_river_scene_noon_2026_06.py           # dry-run + CSV
    .venv\\Scripts\\python.exe scripts\\dryrun_river_scene_noon_2026_06.py --apply    # write (gated)
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

NOON = time(12, 0, 0)
TBD_START = time(0, 0, 0)  # is_time_tbd sentinel (start 00:00 + end NULL)

_REPORT_PATH = _ROOT / "river_scene_noon_candidates.csv"


@dataclass(frozen=True)
class NoonRow:
    id: str
    date: date
    title: str
    source_url: str
    start_time: time | None
    end_time: time | None


def classify_noon(refetch_ok: bool, refetched_start: time | None) -> str:
    """Pure classifier from the re-fetch outcome. See module docstring."""
    if not refetch_ok:
        return "unverified"
    if refetched_start is None:
        return "fabricated"
    if refetched_start == NOON:
        return "legit_noon"
    return "stale_noon"


def _load_noon_rows() -> list[NoonRow]:
    from app.db.database import SessionLocal
    from app.db.models import Event

    out: list[NoonRow] = []
    with SessionLocal() as session:
        rows = (
            session.query(Event)
            .filter(
                Event.status == "live",
                Event.source == "river_scene_import",
                Event.start_time == NOON,
            )
            .all()
        )
        for e in rows:
            out.append(
                NoonRow(
                    id=e.id,
                    date=e.date,
                    title=e.title,
                    source_url=e.source_url or "",
                    start_time=e.start_time,
                    end_time=e.end_time,
                )
            )
    return out


def _build_verified_client():
    import certifi
    import httpx

    from app.contrib.river_scene import EVENT_PAGE_HTTP_TIMEOUT, _headers

    return httpx.Client(
        timeout=EVENT_PAGE_HTTP_TIMEOUT,
        headers=_headers(),
        follow_redirects=True,
        verify=certifi.where(),
    )


def _refetch_start_time(client, url: str, on_date: date) -> tuple[bool, time | None]:
    """Re-fetch the article and report (ok, start_time). ``on_date`` is passed as
    ``today`` so the parser's past-date skip never fires for a known-date row."""
    from app.contrib.river_scene import fetch_and_parse_event

    try:
        rse = fetch_and_parse_event(url, client=client, today=on_date)
    except Exception:
        return (False, None)
    if rse is None:
        return (False, None)
    return (True, rse.start_time)


def run(*, apply: bool = False) -> tuple[Counter, list[tuple[NoonRow, str, time | None]]]:
    rows = _load_noon_rows()
    counts: Counter = Counter()
    counts["scanned"] = len(rows)

    # Cache re-fetch by source_url (the farmers-market article backs ~24 rows).
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
        snap = _ROOT / f"river_scene_noon_undo_{stamp}.csv"
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
        w.writerow(
            ["classification", "id", "date", "title", "source_url", "refetched_start_time", "db_end_time"]
        )
        for r, v, ft in sorted(results, key=lambda t: (t[1], t[0].date)):
            w.writerow([v, r.id, r.date, r.title, r.source_url, ft if ft else "", r.end_time or ""])
    return counts, results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (omit = dry-run).")
    args = parser.parse_args()

    counts, results = run(apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN (no DB writes)"
    print(f"\nRiver Scene fabricated-noon cleanup -- {mode}")
    print(f"  river_scene noon rows scanned: {counts['scanned']}")
    print(f"    fabricated (-> Time TBD):    {counts['fabricated']}")
    print(f"    legit_noon (keep):           {counts['legit_noon']}")
    print(f"    stale_noon (flag, separate): {counts['stale_noon']}")
    print(f"    unverified (page gone/fail): {counts['unverified']}")
    print(f"  candidate CSV: {_REPORT_PATH}")

    fabricated = [(r, ft) for (r, v, ft) in results if v == "fabricated"]
    if fabricated:
        print(f"\n  Would convert to 'Time TBD' (start 00:00 / end NULL) -- {len(fabricated)} rows:")
        for r, _ft in sorted(fabricated, key=lambda t: t[0].date):
            print(f"    {r.id[:8]} | {r.date} | {r.title[:55]}")
    stale = [(r, ft) for (r, v, ft) in results if v == "stale_noon"]
    if stale:
        print(f"\n  FLAGGED stale_noon (source lists a real non-noon time; NOT auto-fixed) -- {len(stale)}:")
        for r, ft in sorted(stale, key=lambda t: t[0].date):
            print(f"    {r.id[:8]} | {r.date} | {r.title[:45]} | source says {ft}")
    unver = [r for (r, v, _ft) in results if v == "unverified"]
    if unver:
        print(f"\n  unverified (article unreachable; left untouched) -- {len(unver)}:")
        for r in sorted(unver, key=lambda x: x.date):
            print(f"    {r.id[:8]} | {r.date} | {r.title[:45]}")
    if not args.apply and counts["fabricated"]:
        print("\n  Review, then re-run with --apply to write (prod-data gate; undo snapshot saved first).")


if __name__ == "__main__":
    main()
