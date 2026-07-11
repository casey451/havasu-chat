"""Data-freshness heartbeat for the scheduled scrape pipelines.

Sister script to ``scripts/check_sources_health.py``. That one probes whether the
external upstreams are *reachable*; this one asks the complementary question the
reachability probe explicitly punts on: **did the pipeline actually land fresh
rows in the database recently, or did a scraper silently start returning zero?**

The canonical failure this guards against (per the discovery plan, workstream I):
River Scene's workflow keeps "succeeding" green on GitHub Actions, but a layout
change broke the parser and it has quietly ingested nothing for a week. The
Actions run is green, the upstream is reachable, and no one is paged. This check
queries the catalog directly, so a frozen pipeline trips it even when everything
upstream looks fine.

Scope (V1): the two event pipelines that run on a frequent cron and carry a
reliable per-row ingest timestamp --

    river_scene_import   river-scene-events.yml   Mon/Wed/Fri
    go_lake_havasu       golakehavasu-events.yml  Tue/Thu/Sat

Each scrape run either inserts a new event (``created_at = now``) or merges a
re-seen one (``scraped_at = now``; ``app/events/dedup.py``), so
``max(greatest(created_at, scraped_at))`` per source advances whenever a run
produces at least one payload, and freezes the moment a scraper goes silent.

Deliberately NOT covered in V1 (no reliable "ran-recently" column -- would be
noisy): parks-rec Programs (``updated_at`` only bumps on an actual field change),
go_lake_havasu partner Providers (re-loads don't touch a timestamp), and gas
prices (kept in a conditions cache with its own staleness handling). When these
need coverage, the right move is the ``ingest_runs`` heartbeat table the plan
names as V2 -- a row written per scrape run regardless of dedup outcome -- not a
brittle recency query bolted on here.

Usage
-----
    python scripts/freshness_check.py
    python scripts/freshness_check.py --json

Exit code: 0 if every configured pipeline is fresh; 1 if any is STALE (last
activity older than its cadence-derived budget) or MISSING (no rows at all,
which usually means the source string drifted or the pipeline never ran). Drop
it into a daily GitHub Actions workflow; a non-zero exit fails the run and the
Actions failure email is the page.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

# ---------------------------------------------------------------------------
# Configured pipelines. ``source`` is the exact ``Event.source`` string the live
# scheduled workflow writes (the ``scripts/*_pull.py`` contrib path), NOT the
# newer ``app/events/scrapers`` registry keys -- those run via scrape_events.py,
# which is not what the crons invoke. ``max_age_hours`` = longest scheduled gap
# between runs + one full extra cycle, so a single skipped run never pages.
# ---------------------------------------------------------------------------


# Two freshness modes:
#   "event_rows"  — max(created_at/scraped_at) over Event.source. For the
#                   established auto-approve pipelines whose runs reliably land
#                   published Event rows; MISSING == broken (pages).
#   "ingest_run"  — max(ran_at) over the ingest_runs heartbeat (WS12). For the
#                   review-queue-first connectors: a run that finds nothing (or
#                   whose rows sit pending) still stamps ran_at, so this tracks
#                   the SCRAPE not the publish. A connector that has never run
#                   (cron not wired yet) reports PENDING (informational, does NOT
#                   page); one that ran before and then went quiet reports STALE
#                   (pages) — that is the "cron broke" signal.
@dataclass(frozen=True)
class SourceCheck:
    label: str
    source: str
    cadence: str
    max_age_hours: float
    mode: str = "event_rows"


SOURCE_CHECKS: list[SourceCheck] = [
    SourceCheck(
        label="Events: River Scene",
        source="river_scene_import",
        cadence="Mon/Wed/Fri (river-scene-events.yml)",
        # Longest gap Fri->Mon = 3 days; +1 cycle (2 days) of slack = 5 days.
        max_age_hours=120.0,
    ),
    SourceCheck(
        label="Events: GoLakeHavasu",
        source="go_lake_havasu",
        cadence="Tue/Thu/Sat (golakehavasu-events.yml)",
        # Longest gap Sat->Tue = 3 days; +1 cycle of slack = 5 days.
        max_age_hours=120.0,
    ),
    # --- WS12 connectors (ingest_run heartbeat) -----------------------------
    # These are review-queue-first and low/seasonal-cadence, so they are tracked
    # by the run-heartbeat, not by published rows. PENDING until their first
    # cron run — that is expected, not a failure.
    SourceCheck(
        label="WS12: Museum (Squarespace)",
        source="havasu_museum",
        cadence="Weekly Mon (museum-events.yml)",
        max_age_hours=336.0,  # 7d cadence + 1 cycle slack = 14d
        mode="ingest_run",
    ),
    SourceCheck(
        label="WS12: LHC BMX",
        source="lhc_bmx",
        cadence="(cron pending) scrape_events --source lhc_bmx",
        max_age_hours=120.0,
        mode="ingest_run",
    ),
    SourceCheck(
        label="WS12: Havasu Youth fixtures",
        source="havasu_youth",
        cadence="(cron pending) scrape_events --source havasu_youth",
        max_age_hours=120.0,
        mode="ingest_run",
    ),
    SourceCheck(
        label="WS12: Altitude booking (ROLLER)",
        source="altitude_booking",
        cadence="every other day (ws12-connectors.yml)",
        max_age_hours=120.0,
        mode="ingest_run",
    ),
    SourceCheck(
        label="WS12: Split Finger (RunSwift)",
        source="split_finger",
        cadence="every other day (ws12-connectors.yml)",
        max_age_hours=120.0,
        mode="ingest_run",
    ),
]


@dataclass
class Result:
    label: str
    source: str
    status: str  # "OK" / "STALE" / "MISSING"
    freshest: datetime | None  # naive UTC
    age_hours: float | None
    max_age_hours: float


def _to_naive_utc(value: datetime | None) -> datetime | None:
    """Normalize a stored timestamp to naive UTC for comparison.

    ``created_at`` is a plain ``DateTime`` (read back naive, already UTC wall
    time). ``scraped_at`` is ``TZAwareDateTime`` (read back tz-aware, in
    America/Phoenix). Collapse both to naive UTC so ``max()`` is meaningful.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def newest_activity(db: Session, source: str) -> datetime | None:
    """Most recent ingest activity for ``source`` as naive UTC, or None."""
    created = db.scalar(select(func.max(Event.created_at)).where(Event.source == source))
    scraped = db.scalar(select(func.max(Event.scraped_at)).where(Event.source == source))
    candidates = [c for c in (_to_naive_utc(created), _to_naive_utc(scraped)) if c is not None]
    return max(candidates) if candidates else None


def newest_run(db: Session, source: str) -> datetime | None:
    """Most recent non-dry-run ingest_runs heartbeat for ``source`` (naive UTC)."""
    from app.db.models import IngestRun

    ran = db.scalar(
        select(func.max(IngestRun.ran_at)).where(
            IngestRun.source == source,
            IngestRun.dry_run.is_(False),
        )
    )
    return _to_naive_utc(ran)


def evaluate(
    db: Session,
    checks: list[SourceCheck],
    *,
    now: datetime,
) -> list[Result]:
    """Grade every configured pipeline against its freshness budget.

    ``now`` is naive UTC and injectable so tests are deterministic.
    """
    results: list[Result] = []
    for chk in checks:
        if chk.mode == "ingest_run":
            freshest = newest_run(db, chk.source)
            # A connector that has never run (cron not wired / not yet fired) is
            # PENDING — informational, never a page. Only a source that ran and
            # then went quiet is STALE.
            missing_status = "PENDING"
        else:
            freshest = newest_activity(db, chk.source)
            missing_status = "MISSING"
        if freshest is None:
            results.append(
                Result(chk.label, chk.source, missing_status, None, None, chk.max_age_hours)
            )
            continue
        age_hours = (now - freshest).total_seconds() / 3600.0
        status = "STALE" if age_hours > chk.max_age_hours else "OK"
        results.append(
            Result(chk.label, chk.source, status, freshest, age_hours, chk.max_age_hours)
        )
    return results


def _fmt_age(age_hours: float | None) -> str:
    if age_hours is None:
        return "no rows"
    if age_hours < 48:
        return f"{age_hours:.1f}h ago"
    return f"{age_hours / 24:.1f}d ago"


def run() -> list[Result]:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        return evaluate(db, SOURCE_CHECKS, now=now)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check scrape pipelines for silent staleness")
    ap.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    results = run()
    # PENDING (an ingest_run connector that has never fired) is informational,
    # not a page — only STALE / MISSING fail the canary.
    failed = [r for r in results if r.status in ("STALE", "MISSING")]

    if args.as_json:
        print(
            json.dumps(
                {
                    "ok": not failed,
                    "results": [
                        {
                            "label": r.label,
                            "source": r.source,
                            "status": r.status,
                            "freshest": r.freshest.isoformat() if r.freshest else None,
                            "age_hours": round(r.age_hours, 2) if r.age_hours is not None else None,
                            "max_age_hours": r.max_age_hours,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
    else:
        width = max(len(r.label) for r in results)
        print("Pipeline freshness heartbeat\n" + "-" * (width + 40))
        for r in results:
            mark = {
                "OK": "OK   ",
                "STALE": "STALE",
                "MISSING": "MISS ",
                "PENDING": "PEND ",
            }[r.status]
            budget = f"budget {r.max_age_hours / 24:.0f}d"
            print(f"  [{mark}] {r.label.ljust(width)}  {_fmt_age(r.age_hours).ljust(10)} ({budget})")
        print("-" * (width + 40))
        if failed:
            print("  STALE/MISSING pipelines: " + ", ".join(r.label for r in failed))
            print("  -> a scraper may be silently returning zero rows; check its workflow run.")
        else:
            print(f"  all {len(results)} pipelines fresh")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
