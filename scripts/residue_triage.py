"""Residue triage for the parks_rec_calendar + allevents review-queue residue.

Read-only. Implements Casey's residue plan and prints proposed rejects (by id,
for the gated triage workflow) plus the two human-review survivor tables:

parks_rec_calendar:
  * internal-dedup — same normalized title + venue + date + start_time across
    pending siblings is a vision-OCR re-scrape; keep the lowest id, propose the
    rest for reject as duplicate. (Conservative: only collapses true same-slot
    twins, so recurring occurrences on other dates and distinct "Class 2"
    sessions survive.)
  * survivors run through the WS6b lints (app/events/lint) — pre-dawn AM/PM-flip
    suspects and hours-not-events are flagged, not auto-rejected. Do NOT
    blanket-quarantine: free drop-in events legitimately live in this source.

allevents (three-way):
  a. solicitation / commercial-pitch -> propose reject spam.
  b. civic (council/board/member meetings) -> run through the WS5 live matcher;
     matches -> propose reject duplicate; non-matches -> surface.
  c. community-real (music, viewing parties, fundraisers-as-events, camps,
     ribbon-cuttings) -> surface. Music rows are tagged (they render on /night —
     the first live-music content ahead of the Facebook decision).

Nothing here writes. Feed the proposed-reject id lists to
triage-pending-events-apply.yml after Casey's pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution  # noqa: E402
from app.events.dedup import find_duplicate, resolve_venue_entity_id  # noqa: E402
from app.events.lint import (  # noqa: E402
    is_early_activity,
    reads_as_venue_hours,
    suspect_ampm_flip,
)
from app.events.scrapers.base import normalize_event_title  # noqa: E402

_SOLICITATION_RE = re.compile(
    r"\b(fundraiser|donat(e|ion)|breast\s+screening|screening\s+day|tax\s+credit|"
    r"supporting\s+[A-Z0-9]|chipotle|dog\s+training\s+class|"
    r"pilates\s+(with\s+purpose|pop))\b",
    re.I,
)
_CIVIC_RE = re.compile(
    r"\b(city\s+council|council\s+meeting|board\s+meeting|members?\s+meeting|"
    r"general\s+member|commission\s+meeting)\b",
    re.I,
)
_MUSIC_RE = re.compile(
    r"\b(live|acoustic|dj|band|concert|music|festival|feat\.?|"
    r"nights?\s+live|duo|jam)\b",
    re.I,
)


def _venue_from_notes(notes: str | None) -> str:
    for raw in (notes or "").splitlines():
        line = raw.strip()
        if line.lower().startswith("venue:"):
            return line[6:].strip()
    return ""


def _row(c: Contribution) -> dict:
    return {
        "id": c.id,
        "date": c.event_date.isoformat() if c.event_date else None,
        "time": c.event_time_start.strftime("%H:%M") if c.event_time_start else None,
        "title": c.submission_name or "",
        "venue": _venue_from_notes(c.submission_notes),
        "source_ref": c.source_url or "",
    }


def _pending(db, source: str) -> list[Contribution]:
    stmt = (
        select(Contribution)
        .where(
            Contribution.status == "pending",
            Contribution.entity_type == "event",
            Contribution.source == source,
        )
        .order_by(Contribution.event_date, Contribution.id)
    )
    return list(db.scalars(stmt))


def triage_parks(db) -> dict:
    rows = _pending(db, "parks_rec_calendar")
    seen: dict[tuple, int] = {}
    internal_dup: list[dict] = []
    survivors: list[Contribution] = []
    for c in rows:
        key = (
            normalize_event_title(c.submission_name or ""),
            _venue_from_notes(c.submission_notes).lower(),
            c.event_date.isoformat() if c.event_date else "",
            c.event_time_start.strftime("%H:%M") if c.event_time_start else "",
        )
        if key in seen:
            d = _row(c)
            d["kept"] = seen[key]
            internal_dup.append(d)
        else:
            seen[key] = c.id
            survivors.append(c)

    clean: list[dict] = []
    flagged: list[dict] = []
    for c in survivors:
        title, venue = c.submission_name or "", _venue_from_notes(c.submission_notes)
        early_ok = is_early_activity(title, venue)
        issues = []
        if suspect_ampm_flip(c.event_time_start, early_ok=early_ok):
            issues.append("pre-dawn AM/PM?")
        if reads_as_venue_hours(title):
            issues.append("reads as hours")
        d = _row(c)
        if issues:
            d["lint"] = ", ".join(issues)
            flagged.append(d)
        else:
            clean.append(d)
    return {"internal_dup": internal_dup, "clean": clean, "flagged": flagged}


def triage_allevents(db) -> dict:
    rows = _pending(db, "allevents")
    solicitation: list[dict] = []
    civic_dup: list[dict] = []
    civic_surface: list[dict] = []
    community: list[dict] = []
    for c in rows:
        title = c.submission_name or ""
        d = _row(c)
        if _SOLICITATION_RE.search(title):
            solicitation.append(d)
        elif _CIVIC_RE.search(title):
            venue_id = resolve_venue_entity_id(db, d["venue"] or None)
            dup = (
                find_duplicate(
                    db,
                    venue_entity_id=venue_id,
                    start_date=c.event_date,
                    start_time_obj=c.event_time_start,
                    normalized_title=normalize_event_title(title),
                )
                if c.event_date
                else None
            )
            if dup is not None:
                d["matched_event"] = f"{dup.id} ({dup.title})"
                civic_dup.append(d)
            else:
                civic_surface.append(d)
        else:
            if _MUSIC_RE.search(title):
                d["music"] = True
            community.append(d)
    return {
        "solicitation": solicitation,
        "civic_dup": civic_dup,
        "civic_surface": civic_surface,
        "community": community,
    }


def _ids(rows: list[dict]) -> str:
    return " ".join(str(r["id"]) for r in rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Residue triage (read-only)")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)

    with SessionLocal() as db:
        parks = triage_parks(db)
        alle = triage_allevents(db)

    if args.as_json:
        print(json.dumps({"parks": parks, "allevents": alle}, indent=2))
        return 0

    print("=== PARKS_REC residue ===")
    print(f"[propose reject: duplicate] internal-dup ({len(parks['internal_dup'])})")
    print("  ids:", _ids(parks["internal_dup"]))
    for r in parks["internal_dup"]:
        print(f"    {r['id']:>6} {r['date']} {r['time']} {r['title'][:44]:<44} (dup of {r['kept']})")
    print(f"\n[SURFACE — clean survivors] ({len(parks['clean'])})")
    for r in parks["clean"]:
        print(f"    {r['id']:>6} {r['date']} {(r['time'] or '—'):<5} {r['title'][:46]:<46} {r['venue'][:22]}")
    print(f"\n[SURFACE — lint-flagged survivors] ({len(parks['flagged'])})")
    for r in parks["flagged"]:
        print(f"    {r['id']:>6} {r['date']} {(r['time'] or '—'):<5} {r['title'][:40]:<40} !{r['lint']}")

    print("\n=== ALLEVENTS residue ===")
    print(f"[propose reject: spam] solicitation ({len(alle['solicitation'])})")
    print("  ids:", _ids(alle["solicitation"]))
    for r in alle["solicitation"]:
        print(f"    {r['id']:>6} {r['date']} {r['title'][:52]}")
    print(f"\n[propose reject: duplicate] civic-matched-live ({len(alle['civic_dup'])})")
    print("  ids:", _ids(alle["civic_dup"]))
    for r in alle["civic_dup"]:
        print(f"    {r['id']:>6} {r['date']} {r['title'][:40]:<40} -> {r.get('matched_event','')}")
    print(f"\n[SURFACE — civic non-matched] ({len(alle['civic_surface'])})")
    for r in alle["civic_surface"]:
        print(f"    {r['id']:>6} {r['date']} {r['title'][:52]}")
    print(f"\n[SURFACE — community] ({len(alle['community'])})")
    for r in alle["community"]:
        tag = " ♪night" if r.get("music") else ""
        print(f"    {r['id']:>6} {r['date']} {(r['time'] or '—'):<5} {r['title'][:44]:<44}{tag}  {r['source_ref'][:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
