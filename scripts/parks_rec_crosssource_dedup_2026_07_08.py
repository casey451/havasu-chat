"""WS6b cross-source dedup (2026-07-08): retire the FLYER copy of a P&R activity
when an authoritative WebTrac copy of the same activity exists on the same date.

The flyer (vision-parsed, `event_url` = `…/185/Parks-Recreation#cal|…`) and the
WebTrac registration record (`event_url` = `register.lhcaz.gov/webtrac/…iteminfo…
FMID=…`) both land as separate live events because the reconciler keys on
date+title+TIME+venue and the two sources disagree on TIME (e.g. Jul 8 Kids Pizza
Party: flyer 3:00 PM vs WebTrac 5:15 PM). WebTrac is the authority, so the flyer
copy is demoted to ``status=pending_review`` (out of the calendar/ICS, into the
review queue), keeping the WebTrac copy live.

Match = SAME date + title similarity (one normalized title is a prefix of the
other, OR token-set Jaccard >= 0.6). Conservative: recurring same-title-different-
DATE classes (line dancing, e-sports) never pair; only same-DATE flyer↔WebTrac.

PROD DB WRITE — dry-run default; ``--apply`` writes + undo CSV. Reversible.
    .venv\\Scripts\\python.exe scripts/parks_rec_crosssource_dedup_2026_07_08.py          # dry-run
    .venv\\Scripts\\python.exe scripts/parks_rec_crosssource_dedup_2026_07_08.py --apply
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_UNDO_CSV = "parks_rec_crosssource_dedup_undo_2026-07-08.csv"
_HELD_STATUS = "pending_review"
_FLYER = "%/185/Parks-Recreation#cal|%"
_WEBTRAC = "%register.lhcaz.gov/webtrac%"
_JACCARD_MIN = 0.6


def _toks(title: str) -> set[str]:
    return {w for w in re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower()).split() if w}


def _similar(a: str, b: str) -> bool:
    na = re.sub(r"[^a-z0-9 ]+", " ", (a or "").lower()).strip()
    nb = re.sub(r"[^a-z0-9 ]+", " ", (b or "").lower()).strip()
    if not na or not nb:
        return False
    if na.startswith(nb) or nb.startswith(na):
        return True
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= _JACCARD_MIN


def _live(db, url_like: str) -> list[Event]:
    return list(db.scalars(
        select(Event).where(Event.status == "live", Event.event_url.like(url_like))
        .order_by(Event.date, Event.start_time)
    ).all())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retire flyer copies superseded by WebTrac.")
    ap.add_argument("--apply", action="store_true", help="write (else dry-run)")
    args = ap.parse_args(argv)
    dry = not args.apply

    undo_rows: list[dict] = []
    with SessionLocal() as db:
        flyers = _live(db, _FLYER)
        webtrac = _live(db, _WEBTRAC)
        wt_by_date: dict[object, list[Event]] = {}
        for w in webtrac:
            wt_by_date.setdefault(w.date, []).append(w)

        for f in flyers:
            match = next((w for w in wt_by_date.get(f.date, []) if _similar(f.title, w.title)), None)
            if match is None:
                continue
            undo_rows.append({
                "flyer_id": f.id, "flyer_title": f.title, "flyer_time": str(f.start_time),
                "webtrac_id": match.id, "webtrac_title": match.title,
                "webtrac_time": str(match.start_time), "date": str(f.date),
                "old_status": f.status,
            })
            if not dry:
                f.status = _HELD_STATUS
        if not dry:
            db.commit()

    if not dry and undo_rows:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(undo_rows[0].keys()))
            w.writeheader()
            w.writerows(undo_rows)

    verb = "would retire" if dry else "RETIRED"
    print(f"live flyer events: {len(undo_rows) and '...'}  cross-source pairs {verb}: {len(undo_rows)}")
    print("  (flyer copy -> pending_review; WebTrac copy stays live)\n")
    for r in undo_rows:
        print(f"  {r['date']}  RETIRE flyer {r['flyer_title']!r} @ {r['flyer_time']} "
              f"({str(r['flyer_id'])[:8]})")
        print(f"            KEEP WebTrac {r['webtrac_title']!r} @ {r['webtrac_time']} "
              f"({str(r['webtrac_id'])[:8]})")
    if dry:
        print("\nDRY RUN — no DB writes. Re-run with --apply (prod-data gate).")
    else:
        print(f"\nAPPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
