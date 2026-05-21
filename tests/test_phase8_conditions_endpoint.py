"""Phase 8a — GET /api/conditions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.conditions.cache import upsert_source
from app.conditions.constants import SOURCE_AIRNOW, SOURCE_NWS_CURRENT
from app.db.database import SessionLocal
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_api_conditions_returns_shape(client: TestClient) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_AIRNOW,
            {
                "current_aqi": 47,
                "current_aqi_parameter": "O3",
                "aqi_source_station_name": "Blythe",
                "aqi_source_state_code": "CA",
                "aqi_source_distance_mi": 60,
            },
            now=now,
        )
        upsert_source(
            db,
            SOURCE_NWS_CURRENT,
            {"temperature_f": 108.0},
            now=now,
        )
        db.commit()

    r = client.get("/api/conditions")
    assert r.status_code == 200
    body = r.json()
    assert body["current_aqi"] == 47
    assert body["current_temp_f"] == 108.0
    assert body["aqi_source_station_name"] == "Blythe"
    assert "aqi_updated_at_iso" in body
