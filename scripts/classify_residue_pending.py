"""Classify remaining pending event contributions into 3 triage buckets (read-only).

For the residue left after the date/year quarantine (parks_rec_calendar future-2026,
allevents future), decide what is actually worth a human's time:

  1. duplicate-of-live — the WS5 matcher (venue + date + fuzzy title + time window,
     app/events/dedup.find_duplicate) finds a LIVE event twin. Many parks_rec rows
     predate the WebTrac reconciliation and are already live under WebTrac
     provenance; allevents re-lists our own sources. Propose: reject reason=duplicate
     (reversible).
  2. spam / off-mission — donation solicitations, tax-credit asks, member/board
     meetings, ad-like "workshops". Propose: reject.
  3. residue — genuinely-new, no live twin, not spam. THESE are the human-review
     table (printed with full source_ref links).

Read-only: writes nothing. Feed the bucket-1/2 ids to triage_pending_events.py
(--ids) to reject; surface bucket 3.

Usage:
    python scripts/classify_residue_pending.py
    python scripts/classify_residue_pending.py --source parks_rec_calendar --json
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
from app.events.scrapers.base import normalize_event_title  # noqa: E402

_DEFAULT_SOURCES = ["parks_rec_calendar", "allevents"]

# Conservative spam / off-mission signals — solicitations and org-internal
# meetings that are not public events. Kept tight so real events fall through to
# the residue bucket for human eyes rather than being auto-proposed for reject.
_SPAM_RE = re.compile(
    r"\b(donate|donation|tax\s+credit|foundation\s*[-–]\s*donate|"
    r"testosterone|members?\s+meeting|general\s+member|board\s+meeting)\b",
    re.I,
)


def _venue_from_notes(notes: str | None) -> str:
    for raw in (notes or "").splitlines():
        line = raw.strip()
        if line.lower().startswith("venue:"):
            return line[6:].strip()
    return ""


def classify(sources: list[str]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {"duplicate": [], "spam": [], "residue": []}
    with SessionLocal() as db:
        stmt = (
            select(Contribution)
            .where(
                Contribution.status == "pending",
                Contribution.entity_type == "event",
                Contribution.source.in_(sources),
            )
            .order_by(Contribution.source, Contribution.event_date, Contribution.id)
        )
        for c in db.scalars(stmt):
            title = c.submission_name or ""
            venue = _venue_from_notes(c.submission_notes)
            row = {
                "id": c.id,
                "source": c.source,
                "date": c.event_date.isoformat() if c.event_date else None,
                "time": c.event_time_start.strftime("%H:%M") if c.event_time_start else None,
                "title": title,
                "venue": venue,
                "source_ref": c.source_url or "",
            }
            if c.event_date is None:
                buckets["residue"].append(row)
                continue
            venue_id = resolve_venue_entity_id(db, venue or None)
            dup = find_duplicate(
                db,
                venue_entity_id=venue_id,
                start_date=c.event_date,
                start_time_obj=c.event_time_start,
                normalized_title=normalize_event_title(title),
            )
            if dup is not None:
                row["matched_event"] = f"{dup.id} ({dup.title})"
                buckets["duplicate"].append(row)
            elif _SPAM_RE.search(title):
                buckets["spam"].append(row)
            else:
                buckets["residue"].append(row)
    return buckets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Classify pending residue into triage buckets")
    ap.add_argument("--source", action="append", dest="sources", metavar="SOURCE")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)
    sources = args.sources or _DEFAULT_SOURCES

    buckets = classify(sources)
    if args.as_json:
        print(json.dumps(buckets, indent=2))
        return 0

    total = sum(len(v) for v in buckets.values())
    print(f"RESIDUE CLASSIFICATION — {total} pending rows across {sources}\n")
    for name in ("duplicate", "spam", "residue"):
        rows = buckets[name]
        print(f"### {name}  ({len(rows)})")
        if name in ("duplicate", "spam"):
            print("  ids:", " ".join(str(r["id"]) for r in rows))
        for r in rows:
            extra = f"  -> live {r['matched_event']}" if name == "duplicate" else ""
            ref = f"  {r['source_ref']}" if name == "residue" else ""
            print(f"    {r['id']:>6} {r['date']} {(r['time'] or '—'):<5} "
                  f"{(r['title'] or '')[:46]:<46} {(r['venue'] or '')[:20]:<20}{extra}{ref}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
