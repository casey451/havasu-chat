"""P1 residual — repoint the SpongeBob Summer Free Movie's wrong link.

Finding 21: the live "Summer Free Movies 'Spongebob Square Pants' Star Cinemas"
row (2026-06-15) has an ``event_url`` pointing at a *Sonic the Hedgehog 3*
RiverScene article — the wrong movie. Repoint it to the same target the sibling
Clifford screening uses (the Star Cinemas page), read live from that row so this
is literally "the same target Clifford uses," not a guessed constant.

One-row prod write. Dry-run prints before/after and writes nothing; ``--apply``
is gated and saves a timestamped undo snapshot first. Defensive: it only touches
a row whose title says SpongeBob and whose current url still points at the wrong
"sonic" article — so a re-run (or a row already fixed) is a safe no-op.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\dryrun_fix_spongebob_movie_link_2026_06.py          # dry-run
    .venv\\Scripts\\python.exe scripts\\dryrun_fix_spongebob_movie_link_2026_06.py --apply   # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _clifford_target(session) -> str | None:
    """The event_url the sibling Clifford Summer Free Movie uses."""
    from app.db.models import Event

    row = (
        session.query(Event)
        .filter(
            Event.status == "live",
            Event.title.ilike("%clifford%"),
            Event.title.ilike("%free movie%"),
        )
        .first()
    )
    return (row.event_url or "").strip() if row else None


def run(*, apply: bool = False) -> dict:
    from app.db.database import SessionLocal
    from app.db.models import Event

    with SessionLocal() as session:
        target = _clifford_target(session)
        candidate = (
            session.query(Event)
            .filter(
                Event.status == "live",
                Event.title.ilike("%spongebob%"),
                Event.title.ilike("%free movie%"),
                Event.event_url.ilike("%sonic%"),
            )
            .one_or_none()
        )
        result = {
            "target": target,
            "found": candidate is not None,
            "id": candidate.id if candidate else None,
            "title": candidate.title if candidate else None,
            "old_url": candidate.event_url if candidate else None,
            "applied": False,
        }
        if candidate is None or not target:
            return result
        if apply:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snap = _ROOT / f"spongebob_link_undo_{stamp}.csv"
            with snap.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["id", "old_event_url"])
                w.writerow([candidate.id, candidate.event_url])
            candidate.event_url = target
            session.commit()
            result["applied"] = True
            result["snapshot"] = str(snap)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the change (omit = dry-run).")
    args = parser.parse_args()

    r = run(apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN (no DB writes)"
    print(f"\nSpongeBob movie link repoint -- {mode}")
    print(f"  Clifford target (new url): {r['target']}")
    if not r["found"]:
        print("  No matching SpongeBob row with a wrong 'sonic' url found (already fixed or absent). No-op.")
        return
    if not r["target"]:
        print("  Could not read Clifford's target url; aborting without change.")
        return
    print(f"  row id:    {r['id']}")
    print(f"  title:     {r['title']}")
    print(f"  BEFORE url: {r['old_url']}")
    print(f"  AFTER  url: {r['target']}")
    if r.get("applied"):
        print(f"  undo snapshot: {r['snapshot']}")
    else:
        print("\n  Review before/after, then re-run with --apply to write (prod-data gate; snapshot saved first).")


if __name__ == "__main__":
    main()
