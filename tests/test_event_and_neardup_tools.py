"""Unit tests for the pure logic of the event deduper, near-dup finder, and the
deactivate-by-id helper (the last two category-cleanup follow-ups).
"""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.deactivate_entities import ids_from_csv
from scripts.dedup_events import exact_occurrence_key, plan, series_key
from scripts.find_near_dups import classify_cluster


def _ev(eid, name="Lap Swim", address="100 Park Ave", start_date="2026-06-15",
        start_time="06:00:00", recurrence_rule=None, created_ts=0.0):
    class _C:
        def __init__(self, ts):
            self._ts = ts

        def timestamp(self):
            return self._ts

    return {"entity_id": eid, "name": name, "slug": eid, "address": address,
            "start_date": start_date, "start_time": start_time,
            "recurrence_rule": recurrence_rule, "created_at": _C(created_ts)}


# --- event keys ------------------------------------------------------------

def test_exact_key_same_occurrence_matches() -> None:
    assert exact_occurrence_key("Lap Swim", "100 Park Ave", "2026-06-15", "06:00:00") == \
        exact_occurrence_key("lap  swim!", "100 Park Ave.", "2026-06-15", "06:00:00")


def test_exact_key_different_date_differs() -> None:
    a = exact_occurrence_key("Lap Swim", "100 Park", "2026-06-15", "06:00:00")
    b = exact_occurrence_key("Lap Swim", "100 Park", "2026-06-16", "06:00:00")
    assert a != b


def test_exact_key_requires_date() -> None:
    assert exact_occurrence_key("Lap Swim", "100 Park", None, "06:00:00") is None
    assert exact_occurrence_key(None, "100 Park", "2026-06-15", None) is None


def test_series_key_groups_same_name_venue() -> None:
    assert series_key("Farmers Market", "Main St") == series_key("farmers market", "main st")
    assert series_key("Farmers Market", "Main St") != series_key("Farmers Market", "Other Rd")


# --- plan: collapse exact dups, never distinct dates -----------------------

def test_plan_collapses_exact_duplicate_occurrences() -> None:
    rows = [_ev("a", created_ts=1.0), _ev("b", created_ts=2.0)]  # same occurrence twice
    deactivate, series = plan(rows)
    assert len(deactivate) == 1  # one survives, one dropped
    assert deactivate[0]["entity_id"] in {"a", "b"}


def test_plan_never_collapses_distinct_dates_and_reports_series() -> None:
    rows = [
        _ev("d1", start_date="2026-06-15"),
        _ev("d2", start_date="2026-06-16"),
        _ev("d3", start_date="2026-06-17"),
    ]
    deactivate, series = plan(rows)
    assert deactivate == []  # different dates => never merged
    assert len(series) == 1 and len(series[0]) == 3  # surfaced as one recurring series


def test_plan_survivor_prefers_recurrence_rule() -> None:
    rows = [_ev("plain", created_ts=5.0), _ev("canonical", recurrence_rule="FREQ=WEEKLY", created_ts=1.0)]
    deactivate, _ = plan(rows)
    assert {r["entity_id"] for r in deactivate} == {"plain"}  # canonical series row kept


# --- near-dup classification ----------------------------------------------

def test_classify_three_addresses_is_chain() -> None:
    rows = [{"address": "1 A St"}, {"address": "2 B St"}, {"address": "3 C St"}]
    assert classify_cluster(rows) == "likely-chain"


def test_classify_two_rows_is_review() -> None:
    rows = [{"address": "1 A St"}, {"address": "1 A St"}]
    assert classify_cluster(rows) == "review"


# --- deactivate ids_from_csv ----------------------------------------------

def test_ids_from_csv(tmp_path: Path) -> None:
    p = tmp_path / "c.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "name"])
        w.writerow(["e1", "X"])
        w.writerow(["", "blank"])
        w.writerow(["e2", "Y"])
    assert ids_from_csv(p) == ["e1", "e2"]
