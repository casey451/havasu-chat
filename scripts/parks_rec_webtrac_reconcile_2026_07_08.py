"""WS6b Phase 1 — reconcile live Parks & Rec FLYER events against the WebTrac
registration catalog (the datetime/venue AUTHORITY). WebTrac wins on conflict.

Generalizes ``scripts/parks_rec_crosssource_dedup_2026_07_08.py`` (which retired
only exact-date title matches). Drives the pure reconciler
(:mod:`app.contrib.parks_rec_reconcile`) + the event lint
(:mod:`app.events.lint`), classifying every live flyer event as:

  * ``supersede``          → retire the flyer (status live -> pending_review); the
    WebTrac twin stays live. Applied.
  * ``quarantine``         → flyer has no WebTrac twin AND trips the lint. Held
    (live -> pending_review). Applied.
  * ``needs_confirmation`` → a WebTrac twin exists but they DISAGREE on time in a
    way that is not an obvious flip (e.g. Glow in the Dark Family Painting: WebTrac
    5:00 PM vs flyer 5:30 PM). **Never written** — flagged in the report for a human
    to confirm with P&R.
  * ``keep``               → clean flyer-only residue; left live.

Only currently-LIVE flyer events are loaded, so re-runs are idempotent. Every
verdict is written to a review CSV; the apply also writes an undo CSV of the rows
it held.

PROD DB WRITE — dry-run default. ``--apply`` writes ``supersede`` + ``quarantine``
(reversible via the undo CSV) and NEVER touches ``needs_confirmation``.
(CLAUDE.md: dry-run -> show counts -> Casey approves -> apply.) The repo .env
DATABASE_URL is Railway's internal host, so the live run happens in CI
(parks-rec-webtrac-reconcile workflow) where the DB secret resolves.

    .venv\\Scripts\\python.exe scripts/parks_rec_webtrac_reconcile_2026_07_08.py           # dry-run
    .venv\\Scripts\\python.exe scripts/parks_rec_webtrac_reconcile_2026_07_08.py --apply   # writes
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.contrib import parks_rec_reconcile as pr  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.lint import lint_event  # noqa: E402

_REVIEW_CSV = "parks_rec_webtrac_reconcile_review_2026-07-08.csv"
_UNDO_CSV = "parks_rec_webtrac_reconcile_undo_2026-07-08.csv"
_HELD_STATUS = "pending_review"
_FLYER = "%/185/Parks-Recreation#cal|%"
_WEBTRAC = "%register.lhcaz.gov/webtrac%"


def _live(db, url_like: str) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .where(Event.status == "live", Event.event_url.like(url_like))
            .order_by(Event.date, Event.start_time)
        ).all()
    )


def _flyer_live(db) -> list[Event]:
    # The synthetic #cal URL lives in event_url; also catch the P&R vision sources.
    return list(
        db.scalars(
            select(Event)
            .where(
                Event.status == "live",
                or_(Event.event_url.like(_FLYER), Event.source.like("%parks_rec_flyer%"),
                    Event.source.like("%parks_rec_calendar%")),
            )
            .order_by(Event.date, Event.start_time)
        ).all()
    )


_FIELDNAMES = [
    "action", "flyer_id", "title", "flyer_date", "flyer_time", "flyer_venue",
    "webtrac_id", "webtrac_date", "webtrac_time", "webtrac_venue", "detail",
]


def _row(v: pr.FlyerVerdict) -> dict:
    f, w = v.flyer, v.webtrac
    return {
        "action": v.action,
        "flyer_id": f.id,
        "title": f.title,
        "flyer_date": f.date.isoformat() if f.date else "",
        "flyer_time": f.start_time.isoformat() if f.start_time else "",
        "flyer_venue": f.location_name,
        "webtrac_id": w.id if w else "",
        "webtrac_date": w.date.isoformat() if w and w.date else "",
        "webtrac_time": w.start_time.isoformat() if w and w.start_time else "",
        "webtrac_venue": w.location_name if w else "",
        "detail": v.detail,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reconcile flyer P&R events vs WebTrac authority.")
    ap.add_argument("--apply", action="store_true", help="write (else dry-run)")
    ap.add_argument(
        "--supersede-only",
        action="store_true",
        help="on --apply, write ONLY supersede (skip quarantine). Use when the "
        "deployed lint is older than intended so the quarantine set can't be trusted.",
    )
    args = ap.parse_args(argv)
    dry = not args.apply

    undo_rows: list[dict] = []
    all_rows: list[dict] = []
    with SessionLocal() as db:
        flyers = _flyer_live(db)
        webtracs = _live(db, _WEBTRAC)
        result = pr.reconcile(flyers, webtracs, lint_fn=lint_event)
        # The write set: supersede (WebTrac wins) + quarantine (lint failure), or
        # supersede-only when the deployed lint can't be trusted for quarantine.
        # needs_confirmation + keep are NEVER written here.
        write_set = list(result.supersede)
        if not args.supersede_only:
            write_set += result.quarantine
        for v in write_set:
            undo_rows.append({
                "action": v.action,
                "flyer_id": v.flyer.id,
                "title": v.flyer.title,
                "old_status": v.flyer.status,
                "webtrac_id": v.webtrac.id if v.webtrac else "",
            })
            if not dry:
                v.flyer.status = _HELD_STATUS
        for bucket in (result.supersede, result.needs_confirmation, result.quarantine, result.keep):
            all_rows.extend(_row(v) for v in bucket)
        if not dry:
            db.commit()

    with open(_REVIEW_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        w.writeheader()
        w.writerows(all_rows)
    if not dry and undo_rows:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as fh:
            uw = csv.DictWriter(fh, fieldnames=list(undo_rows[0].keys()))
            uw.writeheader()
            uw.writerows(undo_rows)

    c = result.counts
    verb = "would" if dry else "DID"
    mode = "supersede ONLY" if args.supersede_only else "supersede + quarantine"
    print(f"live flyer events: {len(flyers)}   live WebTrac events: {len(webtracs)}")
    print(f"reconcile verdicts: {c}")
    print(f"  {verb} write ({mode} -> {_HELD_STATUS}): {len(undo_rows)}")
    print(f"  needs_confirmation (NEVER written — human confirms with P&R): {c[pr.NEEDS_CONFIRMATION]}")

    # Report from the already-materialized `all_rows` dicts — NOT the ORM objects,
    # which are expired + detached after db.commit()/session close (a re-access
    # would raise DetachedInstanceError on an --apply run).
    by_action: dict[str, list[dict]] = {}
    for r in all_rows:
        by_action.setdefault(r["action"], []).append(r)

    nc = by_action.get(pr.NEEDS_CONFIRMATION, [])
    if nc:
        print("\nNEEDS HUMAN CONFIRMATION (WebTrac vs flyer disagree; do NOT assume):")
        for r in nc:
            print(f"  {r['flyer_date']} {r['title']!r}: flyer {r['flyer_time']} vs "
                  f"WebTrac {r['webtrac_time'] or '?'} ({r['detail']})")
    print("\nsupersede (flyer retired, WebTrac kept) — first 15:")
    for r in by_action.get(pr.SUPERSEDE, [])[:15]:
        print(f"  {r['flyer_date']} {r['title']!r} flyer@{r['flyer_time']} "
              f"-> WebTrac@{r['webtrac_time'] or '?'} [{r['detail']}]")
    print("\nquarantine (flyer-only, fails lint) — first 15:")
    for r in by_action.get(pr.QUARANTINE, [])[:15]:
        print(f"  {r['flyer_date']} {r['flyer_time']} {r['title']!r} [{r['detail']}]")

    print(f"\nreview CSV (every verdict): {_REVIEW_CSV}")
    if dry:
        print("DRY RUN — no DB writes. Re-run with --apply (prod-data gate).")
    else:
        print(f"APPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
