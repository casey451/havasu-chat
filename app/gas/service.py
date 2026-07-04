"""Single read-side gas service (v4.4 PR-1, DATA_CONTRACTS §1).

ONE source of truth for gas prices across every surface: the conditions-strip
tile, the home gas panel, and the /gas page all build a :class:`GasBoard` from
the SAME cached payload via :func:`board_from_cache`, so they can never disagree.

The June split this fixes: home said ``$3.69 · >4h ago`` while /gas said
``$4.19 · >6h ago`` — two independent read paths plus a ``>{h}h ago`` label
ceiling. Here the label derives from ``pulled_at`` with honest tiers (§1.3), and
``cheapest(grade)`` is the single method every surface calls, so the cheapest
figure is identical by construction.

Reads the daily payload written by ``app.contrib.gas_prices`` into
``external_conditions_cache`` (``SOURCE_GAS``). No new fetch, no migration — each
surface passes the :class:`~app.conditions.cache.CacheReadResult` it already
reads through its own ``read_source`` seam into :func:`board_from_cache`.
ASCII-only by project convention.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

from sqlalchemy.orm import Session

from app.conditions.cache import CacheReadResult, read_source
from app.conditions.constants import GAS_STALE_AFTER_HOURS, SOURCE_GAS
from app.core.timezone import LAKE_HAVASU_TZ

logger = logging.getLogger(__name__)

# Canonical short grade keys (DATA_CONTRACTS §1.1) <-> the long keys the daily
# pull stores and the current /gas template reads.
GRADE_KEYS: tuple[str, ...] = ("reg", "mid", "prem", "dsl")
_LONG_TO_SHORT: dict[str, str] = {
    "regular": "reg",
    "midgrade": "mid",
    "premium": "prem",
    "diesel": "dsl",
}
_SHORT_TO_LONG: dict[str, str] = {v: k for k, v in _LONG_TO_SHORT.items()}

# Per-station price age past which a row is hidden, and the whole-board age past
# which the strip tile/panel show "prices unavailable" (§1.3).
MAX_AGE = timedelta(days=7)
# Pull-silence threshold for the GAS_PULL_STALE alert (§1.4).
_PULL_STALE = timedelta(hours=12)
_UNAVAILABLE_LABEL = "Prices unavailable -- we're on it"

# GAS_PULL_STALE: warn at most once per hour (§1.4), no new infra.
_stale_lock = threading.Lock()
_last_stale_warn: dict[str, datetime] = {}


@dataclass(frozen=True)
class GasStation:
    name: str
    address: str | None
    directions_url: str
    # keys are GRADE_KEYS; value is None when the station lacks that grade.
    prices: dict[str, float | None]
    observed_at: datetime | None  # per-station price age (naive UTC), None if unknown
    brand: str | None = None
    provider_slug: str | None = None


@dataclass(frozen=True)
class GasBoard:
    stations: list[GasStation]  # already filtered: per-station age <= 7 days
    pulled_at: datetime | None  # last successful pull (naive UTC)
    label: str  # honest tier label, §1.3
    grades_available: list[str]  # subset of GRADE_KEYS
    is_stale: bool  # pull older than the daily staleness threshold
    unavailable: bool  # no data at all, or the whole board is > 7 days old

    def cheapest(self, grade: str = "reg", n: int | None = None) -> list[GasStation]:
        """Stations having ``grade``, cheapest first; ties keep pull order.

        The ONE method every surface calls for "the cheapest station(s)", so the
        strip tile, home panel and /gas page can never show different figures for
        the same grade. Python's sort is stable, so equal prices retain the
        pull's deterministic ordering.
        """
        rows = [s for s in self.stations if isinstance(s.prices.get(grade), (int, float))]
        rows.sort(key=lambda s: s.prices[grade] or 0.0)
        return rows if n is None else rows[:n]

    def city_avg(self, grade: str = "reg") -> float | None:
        vals = [
            p
            for s in self.stations
            if isinstance((p := s.prices.get(grade)), (int, float))
        ]
        return round(sum(vals) / len(vals), 3) if vals else None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _parse_observed(raw: object) -> datetime | None:
    """Parse a per-station ``posted_time`` (ISO string) into naive UTC, or None."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _to_utc_naive(dt)


def _short_prices(raw: object) -> dict[str, float | None]:
    """Normalize a stored ``prices`` dict (long or short keys) to GRADE_KEYS.

    Only positive numbers survive; anything else becomes ``None`` so a surface
    never renders a zero or a junk price.
    """
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, float | None] = {}
    for short, long in _SHORT_TO_LONG.items():
        val = src.get(short)
        if val is None:
            val = src.get(long)
        out[short] = float(val) if isinstance(val, (int, float)) and val > 0 else None
    return out


def directions_url(name: str, address: str | None) -> str:
    dest = ", ".join(p for p in (name, address, "Lake Havasu City AZ") if p)
    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(dest)}"


def _gas_label(pulled_at: datetime, now: datetime) -> str:
    """Honest freshness label (DATA_CONTRACTS §1.3) — no ``>{h}h ago`` ceiling.

    Tiers: <60m -> "Updated {m} min ago"; 1-6h -> "Updated {h}h ago";
    6-24h -> "Updated today {time}" (or "Updated yesterday" if it crossed a
    Phoenix calendar day); 1-7d -> "Updated {weekday}"; >7d handled by the
    caller as unavailable.
    """
    delta = now - pulled_at
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 60:
        return f"Updated {minutes} min ago"
    hours = minutes // 60
    if hours < 6:
        return f"Updated {hours}h ago"
    local_pulled = pulled_at.replace(tzinfo=UTC).astimezone(LAKE_HAVASU_TZ)
    local_now = now.replace(tzinfo=UTC).astimezone(LAKE_HAVASU_TZ)
    if hours < 24:
        if local_pulled.date() == local_now.date():
            clock = local_pulled.strftime("%I:%M %p").lstrip("0")
            return f"Updated today {clock}"
        return "Updated yesterday"
    if delta.days <= 7:
        return f"Updated {local_pulled.strftime('%A')}"
    return _UNAVAILABLE_LABEL


def _warn_pull_stale(age: timedelta, now: datetime) -> None:
    with _stale_lock:
        last = _last_stale_warn.get(SOURCE_GAS)
        if last is not None and (now - last) < timedelta(hours=1):
            return
        _last_stale_warn[SOURCE_GAS] = now
    logger.warning("GAS_PULL_STALE age=%s", age)


def board_from_cache(
    row: CacheReadResult | None, *, now: datetime | None = None
) -> GasBoard:
    """Build a :class:`GasBoard` from a cached SOURCE_GAS row (pure transform).

    This is the single implementation of the honest board; every surface feeds
    the row it already read here, so they all agree.
    """
    now = _to_utc_naive(now) or _utc_now()
    if row is None or not isinstance(row.data, dict):
        return GasBoard([], None, _UNAVAILABLE_LABEL, [], True, True)

    pulled_at = row.fetched_at
    age = now - pulled_at
    board_expired = age > MAX_AGE

    stations: list[GasStation] = []
    for raw in row.data.get("stations") or []:
        if not isinstance(raw, dict):
            continue
        observed = _parse_observed(raw.get("posted_time"))
        # A row is only hidden for age when we KNOW its price is > 7 days old;
        # a missing posted_time defers to the board's pull time.
        age_ref = observed if observed is not None else pulled_at
        if now - age_ref > MAX_AGE:
            continue
        prices = _short_prices(raw.get("prices"))
        if not any(v is not None for v in prices.values()):
            continue
        name = str(raw.get("name") or raw.get("station_name") or "Station").strip()
        address = raw.get("address") or raw.get("cross_street")
        stations.append(
            GasStation(
                name=name,
                address=address,
                directions_url=directions_url(name, address),
                prices=prices,
                observed_at=observed,
                brand=raw.get("brand"),
                provider_slug=raw.get("provider_slug"),
            )
        )

    grades_available = [
        g for g in GRADE_KEYS if any(s.prices.get(g) is not None for s in stations)
    ]
    is_stale = bool(age > timedelta(hours=GAS_STALE_AFTER_HOURS) or row.is_stale)
    if age > _PULL_STALE:
        _warn_pull_stale(age, now)

    # Whole board older than 7 days, or nothing to show: the strip tile/panel go
    # to the "prices unavailable" state. (The /gas page still renders its last
    # table under its own stale banner — it consumes ``stations`` directly.)
    if board_expired or not stations:
        return GasBoard(
            stations,
            pulled_at,
            _UNAVAILABLE_LABEL if (board_expired or not stations) else _gas_label(pulled_at, now),
            grades_available,
            True,
            True,
        )

    return GasBoard(stations, pulled_at, _gas_label(pulled_at, now), grades_available, is_stale, False)


def load_gas_board(db: Session, *, now: datetime | None = None) -> GasBoard:
    """Convenience: read SOURCE_GAS and build the board in one call."""
    now = _to_utc_naive(now) or _utc_now()
    return board_from_cache(read_source(db, SOURCE_GAS, now=now), now=now)


def to_legacy_station_dict(s: GasStation) -> dict[str, object]:
    """A station in the shape the current /gas template expects (long grade keys).

    PR-6 rebuilds that template to read the GasStation directly; until then this
    keeps the page rendering while sourcing every row from the single board.
    """
    return {
        "name": s.name,
        "brand": s.brand,
        "address": s.address,
        "provider_slug": s.provider_slug,
        "prices": {long: s.prices.get(short) for short, long in _SHORT_TO_LONG.items()},
    }
