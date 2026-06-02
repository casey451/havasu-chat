"""Phase B8 — demand-intelligence dashboard (admin, read-only) tests.

Covers: guard redirect when unauthenticated; aggregate correctness on seeded
QueryLog rows; zero-result coverage-gap ranking; per-day trend bucketing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.admin.demand_intel import coverage_gaps, daily_trends, top_intents
from app.db.database import SessionLocal
from app.db.models import QueryLog
from app.main import app


def _wipe(db: Session) -> None:
    db.query(QueryLog).delete()
    db.commit()


def _add(
    db: Session,
    *,
    intent: str,
    category: str | None = None,
    result_count: int = 1,
    days_ago: float = 0.0,
) -> QueryLog:
    created = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_ago)
    row = QueryLog(
        normalized_intent=intent,
        category=category,
        result_count=result_count,
        created_at=created,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def db() -> Session:
    with SessionLocal() as session:
        _wipe(session)
        yield session
        _wipe(session)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def _login(c: TestClient) -> None:
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code in (302, 303)


# --- guard ----------------------------------------------------------------


def test_demand_intel_requires_auth(client: TestClient, db: Session) -> None:
    client.cookies.clear()
    r = client.get("/admin/demand-intel")
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_demand_intel_renders_when_authed(client: TestClient, db: Session) -> None:
    _add(db, intent="find tacos", category="food", result_count=3)
    _login(client)
    r = client.get("/admin/demand-intel")
    assert r.status_code == 200
    assert "Demand intelligence" in r.text
    assert "find tacos" in r.text


# --- top_intents ----------------------------------------------------------


def test_top_intents_groups_and_counts(db: Session) -> None:
    _add(db, intent="kayak rental", result_count=2)
    _add(db, intent="kayak rental", result_count=2)
    _add(db, intent="kayak rental", result_count=0)
    _add(db, intent="boat tour", result_count=5)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    rows = top_intents(db, since=since)
    by_intent = {r["intent"]: r for r in rows}
    assert by_intent["kayak rental"]["total"] == 3
    assert by_intent["kayak rental"]["zero_results"] == 1
    assert by_intent["boat tour"]["total"] == 1
    assert by_intent["boat tour"]["zero_results"] == 0
    # Ordered by total desc -> most-asked first.
    assert rows[0]["intent"] == "kayak rental"


def test_top_intents_window_excludes_old(db: Session) -> None:
    _add(db, intent="recent", days_ago=1)
    _add(db, intent="ancient", days_ago=99)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    intents = {r["intent"] for r in top_intents(db, since=since)}
    assert "recent" in intents
    assert "ancient" not in intents


# --- coverage_gaps --------------------------------------------------------


def test_coverage_gaps_ranks_zero_result_by_frequency(db: Session) -> None:
    # "pickleball court" misses 3x, "dog park" misses 1x; a hit is excluded.
    for _ in range(3):
        _add(db, intent="pickleball court", category="recreation", result_count=0)
    _add(db, intent="dog park", category="parks", result_count=0)
    _add(db, intent="pickleball court", category="recreation", result_count=4)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    gaps = coverage_gaps(db, since=since)
    assert gaps[0]["intent"] == "pickleball court"
    assert gaps[0]["category"] == "recreation"
    assert gaps[0]["misses"] == 3
    assert {"intent": "dog park", "category": "parks", "misses": 1} in gaps


def test_coverage_gaps_empty_when_all_results(db: Session) -> None:
    _add(db, intent="has results", result_count=7)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    assert coverage_gaps(db, since=since) == []


# --- daily_trends ---------------------------------------------------------


def test_daily_trends_buckets_per_day_with_zero_rate(db: Session) -> None:
    # Today: 2 queries, 1 zero -> 0.5 rate. Yesterday: 1 query, 0 zero.
    _add(db, intent="a", result_count=1, days_ago=0)
    _add(db, intent="b", result_count=0, days_ago=0)
    _add(db, intent="c", result_count=2, days_ago=1)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=14)
    trends = daily_trends(db, since=since)
    by_day = {t["day"]: t for t in trends}
    today = (datetime.now(UTC).replace(tzinfo=None)).date().isoformat()
    yesterday = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)).date().isoformat()
    assert by_day[today]["total"] == 2
    assert by_day[today]["zero"] == 1
    assert by_day[today]["zero_rate"] == 0.5
    assert by_day[yesterday]["total"] == 1
    assert by_day[yesterday]["zero"] == 0
    assert by_day[yesterday]["zero_rate"] == 0.0
    # Oldest day first.
    assert trends[0]["day"] == yesterday


def test_daily_trends_omits_empty_days_and_old_rows(db: Session) -> None:
    _add(db, intent="recent", days_ago=2)
    _add(db, intent="old", days_ago=40)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=14)
    days = {t["day"] for t in daily_trends(db, since=since)}
    assert len(days) == 1  # only the in-window day appears
