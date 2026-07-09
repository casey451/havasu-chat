"""CLI: read-only Parks & Rec coverage audit (no LLM, no DB writes).

For the current + next month, reports which Parks & Recreation surfaces return
data and flags any that return 0:

  * webtrac         -- bookable program sections (register.lhcaz.gov)
  * lhcaz_aquatic   -- Aquatic Center PDF slots
  * civic_ical      -- CivicPlus city calendar iCal (catID=23)
  * calendar_image  -- the monthly calendar flyer IMAGE on /185/Parks-Recreation
                       (discovery only -- counts images, does NOT call the LLM)

It also verifies the civic iCal ``catID`` actually carries Events and not just
Meetings (the build brief's "confirm catID=23 or add the Events CID" check): it
breaks the returned civic items into meeting-like vs event-like so a
meetings-only feed is visible.

Prints ``[OK]`` / ``[GAP]`` per surface. Read-only: fetches upstream, writes
nothing. A datacenter IP may not reach some origins -> ``[GAP] (fetch error)``;
re-run from prod before judging.

  .venv\\Scripts\\python.exe scripts/verify_parks_rec_coverage.py
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

_MEETING_RE = re.compile(
    r"\b(meeting|council|commission|board|committee|public hearing|"
    r"planning and zoning|work session|study session)\b",
    re.IGNORECASE,
)


@dataclass
class SurfaceResult:
    name: str
    count: int
    ok: bool
    detail: str = ""
    error: str | None = None


def _window(today: date) -> tuple[tuple[int, int], tuple[int, int]]:
    """(current (year, month), next (year, month))."""
    cm = (today.year, today.month)
    if today.month == 12:
        nm = (today.year + 1, 1)
    else:
        nm = (today.year, today.month + 1)
    return cm, nm


def _in_window(d: date | None, months: set[tuple[int, int]]) -> bool:
    return d is not None and (d.year, d.month) in months


def _audit_webtrac(months: set[tuple[int, int]]) -> SurfaceResult:
    try:
        from app.contrib import webtrac

        sections = webtrac.fetch_all_sections()
        n = sum(1 for s in sections if _in_window(getattr(s, "start_date", None), months))
        return SurfaceResult("webtrac", n, n > 0, f"{len(sections)} total sections")
    except Exception as e:  # noqa: BLE001
        return SurfaceResult("webtrac", 0, False, error=f"{type(e).__name__}: {e}")


def _audit_aquatic(months: set[tuple[int, int]]) -> SurfaceResult:
    try:
        from datetime import date as _date

        from app.contrib import lhcaz_aquatic_pdf

        slots = lhcaz_aquatic_pdf.pull_snapshot()
        n = 0
        for s in slots:
            raw = s.get("slot_date")
            try:
                d = _date.fromisoformat(str(raw)[:10]) if raw else None
            except ValueError:
                d = None
            if _in_window(d, months):
                n += 1
        return SurfaceResult("lhcaz_aquatic", n, n > 0, f"{len(slots)} total slots")
    except Exception as e:  # noqa: BLE001
        return SurfaceResult("lhcaz_aquatic", 0, False, error=f"{type(e).__name__}: {e}")


def _audit_civic(months: set[tuple[int, int]]) -> SurfaceResult:
    try:
        from datetime import datetime as _dt

        from app.events.scrapers.lhc_parks_rec import CIVIC_ICAL_URL, LhcParksRecClient

        hits = LhcParksRecClient().discover({"prefer_ical": True})
        meetings = events = 0
        in_win = 0
        for h in hits:
            start_iso = (h.raw or {}).get("start_iso")
            d = None
            if start_iso:
                try:
                    d = _dt.fromisoformat(str(start_iso)).date()
                except ValueError:
                    d = None
            if _in_window(d, months):
                in_win += 1
            if _MEETING_RE.search(h.name or ""):
                meetings += 1
            else:
                events += 1
        catid = re.search(r"catID=(\d+)", CIVIC_ICAL_URL)
        detail = (
            f"catID={catid.group(1) if catid else '?'}; {len(hits)} upcoming "
            f"(meeting-like={meetings}, event-like={events})"
        )
        if events == 0 and hits:
            detail += " -- CHECK: feed looks meetings-only; add the Events CID"
        return SurfaceResult("civic_ical", in_win, in_win > 0, detail)
    except Exception as e:  # noqa: BLE001
        return SurfaceResult("civic_ical", 0, False, error=f"{type(e).__name__}: {e}")


def _audit_calendar_image(months: set[tuple[int, int]], *, today: date) -> SurfaceResult:
    try:
        from app.contrib.lhc_parks_rec_calendar import (
            discover_calendar_images,
            fetch_gallery_html,
        )

        html = fetch_gallery_html()
        refs = discover_calendar_images(html, today=today)
        in_win = [r for r in refs if (r.year, r.month) in months]
        titles = ", ".join(r.title for r in refs[:4]) or "(none found)"
        return SurfaceResult(
            "calendar_image",
            len(in_win),
            len(in_win) > 0,
            f"{len(refs)} calendar image(s): {titles}",
        )
    except Exception as e:  # noqa: BLE001
        return SurfaceResult("calendar_image", 0, False, error=f"{type(e).__name__}: {e}")


def run_audit(today: date | None = None) -> list[SurfaceResult]:
    today = today or date.today()
    cm, nm = _window(today)
    months = {cm, nm}
    return [
        _audit_webtrac(months),
        _audit_aquatic(months),
        _audit_civic(months),
        _audit_calendar_image(months, today=today),
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.parse_args(argv)

    today = date.today()
    cm, nm = _window(today)
    print(f"=== Parks & Rec coverage audit — {cm[0]}-{cm[1]:02d} + {nm[0]}-{nm[1]:02d} ===")
    results = run_audit(today)
    any_gap = False
    for r in results:
        tag = "[OK] " if r.ok else "[GAP]"
        if not r.ok:
            any_gap = True
        line = f"{tag} {r.name:<16} count={r.count}"
        if r.error:
            line += f"  (fetch error: {r.error})"
        elif r.detail:
            line += f"  {r.detail}"
        print(line)
    if any_gap:
        print("\nNote: [GAP] from a datacenter IP may be a network block, not a real")
        print("coverage gap. Re-run from prod / the proxy before acting on a GAP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
