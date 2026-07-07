"""WS6b Phase 1 — nightly canary: re-verify every FUTURE Parks & Rec flyer event
against the WebTrac registration authority; page (exit non-zero) on drift.

READ-ONLY — SELECTs only, writes nothing. Complements the gated reconciler: once
the flyer copies are reconciled, this catches NEW drift (a fresh flyer scrape that
disagrees with WebTrac, or a flyer-only row that fails lint) before it misleads a
visitor. Drift = a future flyer event classified as:

  * ``needs_confirmation`` — a WebTrac twin disagrees on time (human must confirm),
  * ``supersede``          — a live flyer duplicates a WebTrac twin (should be
                             retired; the reconciler hasn't run/applied yet),
  * ``quarantine``         — a flyer-only row that trips the event lint.

``keep`` rows (clean flyer-only residue) are fine and never page.

    .venv\\Scripts\\python.exe scripts/parks_rec_webtrac_canary.py

Exit 0 = clean; exit 1 = drift found (the CI job fails and pages).
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.contrib import parks_rec_reconcile as pr  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.lint import lint_event  # noqa: E402

_PHOENIX = ZoneInfo("America/Phoenix")
_FLYER = "%/185/Parks-Recreation#cal|%"
_WEBTRAC = "%register.lhcaz.gov/webtrac%"


def _phoenix_today() -> date:
    return datetime.now(_PHOENIX).date()


def _future_live(db, *, today: date, flyer: bool) -> list[Event]:
    if flyer:
        source_pred = or_(
            Event.event_url.like(_FLYER),
            Event.source.like("%parks_rec_flyer%"),
            Event.source.like("%parks_rec_calendar%"),
        )
    else:
        source_pred = Event.event_url.like(_WEBTRAC)
    rows = list(
        db.scalars(
            select(Event)
            .where(Event.status == "live", Event.date >= today, source_pred)
            .order_by(Event.date, Event.start_time)
        ).all()
    )
    # A WebTrac-URL event is never a flyer (even with a combined source) — exclude
    # it from the flyer set so it can't be reconciled against itself.
    if flyer:
        return [r for r in rows if not pr.is_webtrac_event(r)]
    return rows


def main() -> int:
    today = _phoenix_today()
    with SessionLocal() as db:
        flyers = _future_live(db, today=today, flyer=True)
        webtracs = _future_live(db, today=today, flyer=False)
        result = pr.reconcile(flyers, webtracs, lint_fn=lint_event)

    drift = [*result.needs_confirmation, *result.supersede, *result.quarantine]
    print(f"P&R WebTrac canary — future window from {today.isoformat()} (America/Phoenix)")
    print(f"  future flyer events: {len(flyers)}   future WebTrac events: {len(webtracs)}")
    print(f"  verdicts: {result.counts}")

    if not drift:
        print("\nCANARY GREEN — no drift; every future flyer event agrees with WebTrac or is clean residue.")
        return 0

    print(f"\nCANARY RED — {len(drift)} future P&R event(s) drifted from the WebTrac authority:")
    for v in result.needs_confirmation:
        wt = v.webtrac
        print(f"  [needs_confirmation] {v.flyer.date} {v.flyer.title!r}: flyer "
              f"{v.flyer.start_time} vs WebTrac {wt.start_time if wt else '?'} ({v.detail})")
    for v in result.supersede:
        print(f"  [supersede-pending]  {v.flyer.date} {v.flyer.title!r} "
              f"flyer@{v.flyer.start_time} duplicates a live WebTrac twin ({v.detail})")
    for v in result.quarantine:
        print(f"  [quarantine]         {v.flyer.date} {v.flyer.start_time} "
              f"{v.flyer.title!r} fails lint [{v.detail}]")
    print("\nRun scripts/parks_rec_webtrac_reconcile_2026_07_08.py (dry-run) to resolve.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
