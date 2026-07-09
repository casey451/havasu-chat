"""v4.4 PR-1 — the single GasService (DATA_CONTRACTS §1).

Pins the honest-label tiers (§1.3), the >7d hide rules, grade capture, and the
single-board guarantee that the strip tile, home panel and /gas page all derive
their figures from one object.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.conditions.cache import CacheReadResult
from app.core.timezone import LAKE_HAVASU_TZ
from app.gas.service import (
    GRADE_KEYS,
    board_from_cache,
    to_legacy_station_dict,
)


def _row(stations: list[dict], *, fetched_at: datetime, is_stale: bool = False) -> CacheReadResult:
    return CacheReadResult(
        data={"stations": stations}, fetched_at=fetched_at, ttl_seconds=86400, is_stale=is_stale
    )


def _st(name: str, reg: float | None = None, **grades: float) -> dict:
    prices: dict[str, float] = {}
    if reg is not None:
        prices["regular"] = reg
    prices.update({k: v for k, v in grades.items()})
    return {"name": name, "address": f"{name} Rd", "prices": prices}


# ── §1.3 honest label tiers ─────────────────────────────────────────────────


def test_label_minutes() -> None:
    now = datetime(2026, 7, 3, 20, 0, 0)
    board = board_from_cache(_row([_st("A", 3.5)], fetched_at=now - timedelta(minutes=12)), now=now)
    assert board.label == "Updated 12 min ago"


def test_label_hours() -> None:
    now = datetime(2026, 7, 3, 20, 0, 0)
    board = board_from_cache(_row([_st("A", 3.5)], fetched_at=now - timedelta(hours=3)), now=now)
    assert board.label == "Updated 3h ago"
    assert "h ago" in board.label and ">" not in board.label  # no ceiling


def test_label_today_with_time() -> None:
    now = datetime(2026, 7, 3, 22, 0, 0)  # Phoenix 15:00 Jul 3
    pulled = datetime(2026, 7, 3, 14, 0, 0)  # Phoenix 07:00 Jul 3, 8h earlier
    board = board_from_cache(_row([_st("A", 3.5)], fetched_at=pulled), now=now)
    assert board.label == "Updated today 7:00 AM"


def test_label_yesterday_when_day_crossed() -> None:
    now = datetime(2026, 7, 3, 14, 0, 0)  # Phoenix 07:00 Jul 3
    pulled = datetime(2026, 7, 3, 2, 0, 0)  # Phoenix 19:00 Jul 2, 12h earlier
    board = board_from_cache(_row([_st("A", 3.5)], fetched_at=pulled), now=now)
    assert board.label == "Updated yesterday"


def test_label_weekday_within_week() -> None:
    now = datetime(2026, 7, 3, 12, 0, 0)
    pulled = datetime(2026, 7, 1, 12, 0, 0)  # 2 days earlier
    expected = pulled.replace(tzinfo=UTC).astimezone(LAKE_HAVASU_TZ).strftime("%A")
    board = board_from_cache(_row([_st("A", 3.5)], fetched_at=pulled), now=now)
    assert board.label == f"Updated {expected}"


# ── >7d hide rules ──────────────────────────────────────────────────────────


def test_whole_board_over_7d_is_unavailable() -> None:
    now = datetime(2026, 7, 15, 12, 0, 0)
    board = board_from_cache(
        _row([_st("A", 3.5)], fetched_at=now - timedelta(days=8)), now=now
    )
    assert board.unavailable is True
    assert board.is_stale is True
    assert board.stations == []
    assert board.label == "Prices unavailable -- we're on it"


def test_per_station_over_7d_hidden_others_kept() -> None:
    now = datetime(2026, 7, 3, 12, 0, 0)
    fresh = _st("Fresh", 3.5)
    fresh["posted_time"] = (now - timedelta(hours=2)).replace(tzinfo=UTC).isoformat()
    stale = _st("Stale", 3.2)
    stale["posted_time"] = (now - timedelta(days=9)).replace(tzinfo=UTC).isoformat()
    board = board_from_cache(_row([fresh, stale], fetched_at=now - timedelta(hours=1)), now=now)
    names = [s.name for s in board.stations]
    assert names == ["Fresh"]  # the 9-day-old station is hidden
    assert board.unavailable is False


def test_no_data_is_unavailable() -> None:
    board = board_from_cache(None, now=datetime(2026, 7, 3, 12, 0, 0))
    assert board.unavailable is True
    assert board.stations == []


# ── cheapest / grades / normalization ───────────────────────────────────────


def test_cheapest_sorts_and_ties_keep_pull_order() -> None:
    now = datetime(2026, 7, 3, 12, 0, 0)
    stations = [_st("A", 4.0), _st("B", 3.5), _st("C", 3.5), _st("D", 3.9)]
    board = board_from_cache(_row(stations, fetched_at=now - timedelta(hours=1)), now=now)
    order = [s.name for s in board.cheapest("reg")]
    assert order == ["B", "C", "D", "A"]  # 3.5 tie keeps pull order B before C
    assert [s.name for s in board.cheapest("reg", 2)] == ["B", "C"]


def test_grades_available_and_per_grade_cheapest() -> None:
    now = datetime(2026, 7, 3, 12, 0, 0)
    stations = [
        _st("A", 4.0, diesel=4.8),
        _st("B", 3.5),  # no diesel
        _st("C", 3.9, diesel=4.5),
    ]
    board = board_from_cache(_row(stations, fetched_at=now - timedelta(hours=1)), now=now)
    assert set(board.grades_available) == {"reg", "dsl"}
    assert "mid" not in board.grades_available
    # Diesel view drops the station without diesel and sorts by diesel price.
    assert [s.name for s in board.cheapest("dsl")] == ["C", "A"]


def test_zero_and_missing_prices_filtered() -> None:
    now = datetime(2026, 7, 3, 12, 0, 0)
    stations = [_st("Zero", 0.0), _st("Good", 3.5), {"name": "Empty", "prices": {}}]
    board = board_from_cache(_row(stations, fetched_at=now - timedelta(hours=1)), now=now)
    assert [s.name for s in board.stations] == ["Good"]


def test_short_and_long_keys_both_accepted() -> None:
    now = datetime(2026, 7, 3, 12, 0, 0)
    short = {"name": "Short", "prices": {"reg": 3.5, "prem": 4.1}}
    board = board_from_cache(_row([short], fetched_at=now - timedelta(hours=1)), now=now)
    s = board.stations[0]
    assert s.prices["reg"] == 3.5
    assert s.prices["prem"] == 4.1
    assert s.prices["mid"] is None
    assert set(s.prices.keys()) == set(GRADE_KEYS)


def test_legacy_station_dict_shape() -> None:
    now = datetime(2026, 7, 3, 12, 0, 0)
    board = board_from_cache(
        _row([_st("A", 3.5, midgrade=3.8)], fetched_at=now - timedelta(hours=1)), now=now
    )
    d = to_legacy_station_dict(board.stations[0])
    assert d["prices"]["regular"] == 3.5
    assert d["prices"]["midgrade"] == 3.8
    assert d["prices"]["diesel"] is None
    assert "google.com/maps" in board.stations[0].directions_url


# ── staleness threshold vs the 3x/day pull cadence (2026-07-08 canary red) ───


def test_gas_config_ttl_not_shorter_than_stale_threshold() -> None:
    """The gas cache TTL must not silently undercut GAS_STALE_AFTER_HOURS.

    ``board_from_cache`` computes ``is_stale = age > GAS_STALE_AFTER_HOURS OR
    row.is_stale``, and ``row.is_stale`` is driven by ``TTL_BY_SOURCE[SOURCE_GAS]``.
    If the TTL is shorter than the documented threshold it wins the OR and the
    board reads stale sooner than intended — the root cause of the 2026-07-08
    false-red (TTL 8h < 10h threshold).
    """
    from app.conditions.constants import (
        GAS_STALE_AFTER_HOURS,
        SOURCE_GAS,
        TTL_BY_SOURCE,
    )

    assert TTL_BY_SOURCE[SOURCE_GAS] >= GAS_STALE_AFTER_HOURS * 3600


def test_gas_stale_threshold_covers_overnight_pull_gap() -> None:
    """The threshold must exceed the largest normal inter-run gap.

    gas-prices.yml pulls at 06:00 / 13:00 / 20:00 America/Phoenix, so the widest
    normal gap is the overnight 20:00 -> 06:00 stretch (~10h) plus GitHub cron
    lag. Below ~11h the banner false-flags stale every morning.
    """
    from app.conditions.constants import GAS_STALE_AFTER_HOURS

    assert GAS_STALE_AFTER_HOURS >= 11


def test_gas_board_not_stale_within_overnight_gap() -> None:
    """End-to-end reproduction: a 9h-old payload (mid overnight gap) is fresh.

    Feeds ``board_from_cache`` the ``row.is_stale`` that ``read_source`` would
    compute from the live gas TTL at 9h, exactly as the /api/gas path does. Before
    the fix (TTL 8h) this row read stale at 9h and tripped the canary; after it
    (TTL/threshold 12h) neither OR term fires.
    """
    from app.conditions.cache import _is_stale
    from app.conditions.constants import SOURCE_GAS, TTL_BY_SOURCE

    now = datetime(2026, 7, 8, 13, 0, 0)
    pulled = now - timedelta(hours=9)
    row_is_stale = _is_stale(pulled, TTL_BY_SOURCE[SOURCE_GAS], now)
    assert row_is_stale is False  # cache-layer flag (TTL) must not fire at 9h
    board = board_from_cache(
        _row([_st("A", 3.59)], fetched_at=pulled, is_stale=row_is_stale), now=now
    )
    assert board.is_stale is False  # board (threshold OR row flag) agrees
