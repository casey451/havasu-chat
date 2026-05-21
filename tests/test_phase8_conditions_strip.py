"""Phase 8a — home conditions strip."""

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


def test_home_renders_conditions_strip_with_data(client: TestClient) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_CURRENT,
            {"temperature_f": 99.0},
            now=now,
        )
        upsert_source(
            db,
            SOURCE_AIRNOW,
            {
                "current_aqi": 55,
                "current_aqi_parameter": "O3",
                "aqi_source_station_name": "Blythe",
                "aqi_source_state_code": "CA",
                "aqi_source_distance_mi": 60,
            },
            now=now,
        )
        db.commit()

    r = client.get("/home")
    assert r.status_code == 200
    assert "conditions-strip" in r.text
    assert "99°F" in r.text or "99" in r.text
    assert "conditions_strip.js" in r.text
    assert "Conditions data coming soon" not in r.text
