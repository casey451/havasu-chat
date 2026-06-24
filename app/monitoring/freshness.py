"""Unified data-freshness monitor across every scheduled feed.

``scripts/freshness_check.py`` is the original event-only heartbeat (V1): it
catches the two *event* scrape pipelines silently going stale. This module
generalizes that guard to the feeds whose staleness produced the **P0 sitewide
date-desync bug** — gas prices and movie showtimes shown "1–11 days old, labeled
today" — plus the same two event pipelines. One evaluator backs both:

* the cron alert (``scripts/data_freshness_monitor.py``) — a non-zero exit fails
  the GitHub Actions run and the failure email is the page; and
* the admin "Data freshness" table (``app/admin/v1_overview.py``).

Design mirrors the V1 heartbeat: each feed exposes a *probe* returning its
freshest activity timestamp (naive UTC) or ``None``; :func:`evaluate` grades each
against a cadence-derived budget into ``OK`` / ``STALE`` / ``MISSING``. ``now`` is
injectable so the grading is deterministic in tests — this is what lets a
staleness alert be exercised without waiting for a feed to actually rot.

Why this permanently closes the P0 class of bug: the date-desync was a *silent*
staleness (the page rendered, the cron stayed green, nobody was paged). A probe
queries the catalog/cache directly, so a frozen feed trips the budget even when
the upstream is reachable and the workflow is green.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.db.models import Event, MovieShowtime

# Probe = a read-only query that returns a feed's freshest activity as naive UTC.
Probe = Callable[[Session], "datetime | None"]


def to_naive_utc(value: datetime | None) -> datetime | None:
    """Normalize a stored timestamp to naive UTC for comparison.

    Plain ``DateTime`` columns read back naive (already UTC wall time);
    ``TZAwareDateTime`` columns read back tz-aware in America/Phoenix. Collapse
    both so ``max()`` and age subtraction are meaningful. Mirrors the helper in
    ``scripts/freshness_check.py`` (kept independent so neither imports the
    other across the app/scripts boundary).
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


@dataclass(frozen=True)
class FeedCheck:
    """A monitored feed: how to find its freshest row and how old is too old."""

    label: str
    key: str
    cadence: str
    max_age_hours: float
    probe: Probe


@dataclass
class FeedStatus:
    """Grade for one feed at a point in time."""

    label: str
    key: str
    status: str  # "OK" / "STALE" / "MISSING"
    freshest: datetime | None  # naive UTC
    age_hours: float | None
    max_age_hours: float

    @property
    def ok(self) -> bool:
        return self.status == "OK"


# --- probes ---------------------------------------------------------------


def _event_source_probe(source: str) -> Probe:
    """Freshest ingest activity for an ``Event.source`` (created or re-scraped)."""

    def probe(db: Session) -> datetime | None:
        created = db.scalar(select(func.max(Event.created_at)).where(Event.source == source))
        scraped = db.scalar(select(func.max(Event.scraped_at)).where(Event.source == source))
        candidates = [c for c in (to_naive_utc(created), to_naive_utc(scraped)) if c is not None]
        return max(candidates) if candidates else None

    return probe


def _movies_probe(db: Session) -> datetime | None:
    """Freshest showtime scrape (the /movies surface; its own dedicated table)."""
    scraped = db.scalar(select(func.max(MovieShowtime.scraped_at)))
    created = db.scalar(select(func.max(MovieShowtime.created_at)))
    candidates = [c for c in (to_naive_utc(scraped), to_naive_utc(created)) if c is not None]
    return max(candidates) if candidates else None


def _gas_probe(db: Session) -> datetime | None:
    """Last successful gas-price fetch (kept in the conditions cache, not Event)."""
    row = read_source(db, SOURCE_GAS)
    if row is None or row.fetched_at is None:
        return None
    return to_naive_utc(row.fetched_at)


# --- configured feeds -----------------------------------------------------
# ``max_age_hours`` = longest scheduled gap between runs + a full extra cycle of
# slack, so a single skipped run never pages. Crons are in .github/workflows/.

FEED_CHECKS: list[FeedCheck] = [
    FeedCheck(
        label="Events: River Scene",
        key="river_scene_import",
        cadence="odd-day cron (river-scene-events.yml)",
        max_age_hours=120.0,  # 3-day gap + 2-day slack
        probe=_event_source_probe("river_scene_import"),
    ),
    FeedCheck(
        label="Events: GoLakeHavasu",
        key="go_lake_havasu",
        cadence="odd-day cron (golakehavasu-events.yml)",
        max_age_hours=120.0,
        probe=_event_source_probe("go_lake_havasu"),
    ),
    FeedCheck(
        label="Movies: Star Cinemas showtimes",
        key="movie_showtimes",
        cadence="2×/day (star-cinemas-showtimes.yml)",
        max_age_hours=48.0,  # ~16h longest gap + 2 missed runs of slack
        probe=_movies_probe,
    ),
    FeedCheck(
        label="Gas prices",
        key=SOURCE_GAS,
        cadence="3×/day (gas-prices.yml)",
        # P0: gas read 11 days old, labeled "today". A 24h budget pages loudly
        # after a single dead day — the harder "feed is dead" threshold (the
        # softer 10h banner staleness lives in app/conditions/constants.py).
        max_age_hours=24.0,
        probe=_gas_probe,
    ),
]


def evaluate(
    db: Session,
    checks: Sequence[FeedCheck] | None = None,
    *,
    now: datetime,
) -> list[FeedStatus]:
    """Grade every feed against its budget. ``now`` is naive UTC, injectable."""
    selected = list(checks) if checks is not None else FEED_CHECKS
    results: list[FeedStatus] = []
    for chk in selected:
        freshest = chk.probe(db)
        if freshest is None:
            results.append(FeedStatus(chk.label, chk.key, "MISSING", None, None, chk.max_age_hours))
            continue
        age_hours = (now - freshest).total_seconds() / 3600.0
        status = "STALE" if age_hours > chk.max_age_hours else "OK"
        results.append(
            FeedStatus(chk.label, chk.key, status, freshest, age_hours, chk.max_age_hours)
        )
    return results


def run(now: datetime | None = None) -> list[FeedStatus]:
    """Evaluate all feeds against the live DB (opens its own session)."""
    from app.db.database import SessionLocal

    when = now if now is not None else datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        return evaluate(db, now=when)


def fmt_age(age_hours: float | None) -> str:
    if age_hours is None:
        return "no rows"
    if age_hours < 48:
        return f"{age_hours:.1f}h ago"
    return f"{age_hours / 24:.1f}d ago"
