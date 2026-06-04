"""UV robustness (Task 0) — Open-UV primary with a keyless EPA fallback.

No live HTTP: the Open-UV branch self-gates on OPENUV_API_KEY and the EPA branch
is exercised against mocked rows. Verifies the orchestrator prefers Open-UV when
keyed, falls back to the keyless EPA forecast otherwise, and that the api_payload
/ view_model layers attribute the tile to whichever source supplied the number.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.conditions import epa_uv, openuv, uv
from app.conditions.constants import SOURCE_OPENUV

# ----- orchestrator (app/conditions/uv.py) -------------------------------


def test_orchestrator_prefers_openuv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENUV_API_KEY", "test-key")
    with patch.object(openuv, "_get", return_value={"result": {"uv": 7.3, "uv_max": 9.1}}):
        with patch.object(epa_uv, "_get") as epa_get:
            out = uv.fetch_uv_index()
            epa_get.assert_not_called()  # EPA not consulted when Open-UV has data
    assert out["uv_index"] == 7.3
    assert out["uv_source"] == "Open-UV"
    assert out["uv_severity"] == "warning"


def test_orchestrator_falls_back_to_epa_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENUV_API_KEY", raising=False)
    rows = [
        {"DATE_TIME": "JUN/04/2026 10 AM", "UV_VALUE": 6},
        {"DATE_TIME": "JUN/04/2026 12 PM", "UV_VALUE": 9},
        {"DATE_TIME": "JUN/04/2026 02 PM", "UV_VALUE": 4},
    ]
    now = datetime(2026, 6, 4, 12, 0)  # naive local-ish; epa uses now.hour
    with patch.object(epa_uv, "_get", return_value=rows):
        with patch.object(epa_uv, "datetime") as dt:
            dt.now.return_value = now
            out = uv.fetch_uv_index()
    assert out["uv_index"] == 9  # current hour (12 PM) value
    assert out["uv_max"] == 9
    assert out["uv_source"] == "EPA UV index"
    assert out["uv_severity"] == "severe"


def test_orchestrator_returns_empty_when_both_dry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENUV_API_KEY", raising=False)
    with patch.object(epa_uv, "_get", return_value=[]):
        assert uv.fetch_uv_index() == {}


@pytest.mark.parametrize(
    "uv_val,sev",
    [(1.0, "good"), (4.0, "moderate"), (7.0, "warning"), (9.0, "severe")],
)
def test_uv_severity_bands(uv_val: float, sev: str) -> None:
    assert uv.uv_severity(uv_val) == sev


# ----- EPA client (app/conditions/epa_uv.py) -----------------------------


@pytest.mark.parametrize(
    "stamp,hour",
    [
        ("JUN/04/2026 12 AM", 0),
        ("JUN/04/2026 07 AM", 7),
        ("JUN/04/2026 12 PM", 12),
        ("JUN/04/2026 01 PM", 13),
        ("JUN/04/2026 11 PM", 23),
    ],
)
def test_epa_parse_hour(stamp: str, hour: int) -> None:
    assert epa_uv._parse_hour(stamp) == hour


def test_epa_parse_hour_garbage_is_none() -> None:
    assert epa_uv._parse_hour(None) is None
    assert epa_uv._parse_hour("not a date") is None


def test_epa_fetch_falls_back_to_peak_when_hour_missing() -> None:
    rows = [
        {"DATE_TIME": "JUN/04/2026 09 AM", "UV_VALUE": 3},
        {"DATE_TIME": "JUN/04/2026 11 AM", "UV_VALUE": 8},
    ]
    now = datetime(2026, 6, 4, 18, 0)  # 6 PM not in rows -> use peak
    with patch.object(epa_uv, "_get", return_value=rows):
        out = epa_uv.fetch_epa_uv_index(now=now)
    assert out == {"uv_index": 8, "uv_max": 8}


def test_epa_fetch_graceful_on_error() -> None:
    with patch.object(epa_uv, "_get", side_effect=RuntimeError("boom")):
        assert epa_uv.fetch_epa_uv_index() == {}


# ----- attribution passthrough (api_payload + view_model) ----------------


def test_view_model_uv_tile_attributes_to_epa() -> None:
    from app.conditions.cache import invalidate_local_cache, upsert_source
    from app.conditions.view_model import build_conditions_strip_view_model
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_OPENUV,
            {"uv_index": 8, "uv_max": 9, "uv_severity": "severe", "uv_source": "EPA UV index"},
            now=now,
        )
        db.commit()
        invalidate_local_cache(SOURCE_OPENUV)
        vm = build_conditions_strip_view_model(db, now=now)
    uv_tiles = [t for t in vm.tiles if t.kind == "uv"]
    assert len(uv_tiles) == 1
    assert uv_tiles[0].attribution_chip == "EPA UV index"
