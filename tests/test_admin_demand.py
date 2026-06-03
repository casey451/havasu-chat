"""Admin demand dashboard — query-log view (Phase 2 §5a)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.admin.demand import build_demand_view
from app.db.database import SessionLocal
from app.db.models import QueryLog
from app.main import app


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_demand_route_requires_admin_auth() -> None:
    with TestClient(app) as client:
        r = client.get("/admin/demand", follow_redirects=False)
    # Unauthed visitors are bounced to the admin login, never shown the data.
    assert r.status_code in (302, 303, 307, 401, 403)


def test_build_demand_view_empty_window() -> None:
    with SessionLocal() as db:
        # A far-future "now" guarantees an empty window regardless of seed data.
        view = build_demand_view(db, now=_now() + timedelta(days=3650), days=1)
    assert view["total"] == 0
    assert view["top_intents"] == []
    assert view["unserved"] == []
    assert view["unserved_total"] == 0


def test_build_demand_view_top_and_unserved() -> None:
    tag = uuid.uuid4().hex[:8]
    served = f"find_tacos_{tag}"
    empty = f"find_unicorn_groomer_{tag}"
    now = _now()
    rows = [
        QueryLog(normalized_intent=served, category="eat-drink", result_count=5, created_at=now),
        QueryLog(normalized_intent=served, category="eat-drink", result_count=4, created_at=now),
        QueryLog(normalized_intent=empty, category="services", result_count=0, created_at=now),
        QueryLog(normalized_intent=empty, category="services", result_count=0, created_at=now),
        QueryLog(normalized_intent=empty, category="services", result_count=0, created_at=now),
    ]
    with SessionLocal() as db:
        db.add_all(rows)
        db.commit()
        try:
            view = build_demand_view(db, now=now + timedelta(minutes=1), days=30)
            intents = {r["label"]: r["count"] for r in view["top_intents"]}
            unserved = {r["label"]: r["count"] for r in view["unserved"]}
            assert intents.get(served) == 2
            assert intents.get(empty) == 3
            # Unserved = only the 0-result intent (the acquisition list).
            assert unserved.get(empty) == 3
            assert served not in unserved
            assert view["unserved_total"] >= 3
            assert view["total"] >= 5
        finally:
            db.execute(delete(QueryLog).where(QueryLog.normalized_intent.in_([served, empty])))
            db.commit()
