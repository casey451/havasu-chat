"""Phase 4.3 — OSM Overpass client (BaseIngestClient Layer-2 proof)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, RawHit
from app.contrib.osm_overpass_client import (
    OSM_OVERPASS_LIMITER,
    OSM_OVERPASS_USER_AGENT,
    OsmOverpassClient,
    build_query,
)
from app.contrib.rate_limiter import SourceLimiter


def test_build_query_contains_leisure_dog_park_bbox() -> None:
    q = build_query("leisure", "dog_park")
    assert "leisure" in q and "dog_park" in q
    assert "34.43" in q and "-114.41" in q and "34.59" in q and "-114.30" in q
    assert "[out:json]" in q and "out body geom" in q


def test_osm_client_is_base_subclass() -> None:
    assert issubclass(OsmOverpassClient, BaseIngestClient)
    assert OsmOverpassClient.source_name == "osm"


def test_mock_overpass_returns_three_raw_hits() -> None:
    body = {
        "elements": [
            {
                "type": "node",
                "id": 111,
                "lat": 34.5,
                "lon": -114.35,
                "tags": {"name": "Dog Park A", "leisure": "dog_park"},
            },
            {
                "type": "way",
                "id": 222,
                "center": {"lat": 34.51, "lon": -114.36},
                "tags": {"name": "Dog Park B", "leisure": "dog_park"},
            },
            {
                "type": "node",
                "id": 333,
                "tags": {"leisure": "dog_park"},
            },
        ]
    }
    client = OsmOverpassClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = body
    with patch.object(OSM_OVERPASS_LIMITER, "call_with_retry", return_value=mock_resp):
        hits = client.discover({"tag": "leisure", "value": "dog_park"})
    assert len(hits) == 2
    names = {h.name for h in hits}
    assert names == {"Dog Park A", "Dog Park B"}


def test_dedupe_key_shape() -> None:
    client = OsmOverpassClient()
    hit = RawHit(
        source="osm",
        source_stable_id="osm_node_12345",
        name="X",
        raw={},
    )
    assert client.dedupe_key(hit) == "osm_node_12345"


@pytest.mark.parametrize(
    ("tags", "ada", "free"),
    [
        ({"wheelchair": "yes"}, True, None),
        ({"wheelchair": "limited"}, True, None),
        ({"wheelchair": "no"}, False, None),
        ({"fee": "no"}, None, True),
        ({"fee": "yes"}, None, False),
    ],
)
def test_to_entity_payload_wheelchair_and_fee(
    tags: dict[str, Any], ada: bool | None, free: bool | None
) -> None:
    client = OsmOverpassClient()
    hit = EnrichedHit(
        raw_hit=RawHit(
            source="osm",
            source_stable_id="osm_node_1",
            name="Test",
            lat=1.0,
            lng=-1.0,
            raw={"tags": tags},
        )
    )
    payload = client.to_entity_payload(hit)
    if ada is not None:
        assert payload.extension_payloads.get("ada_accessible") is ada
    if free is not None:
        assert payload.extension_payloads.get("free") is free


def test_discover_empty_elements() -> None:
    client = OsmOverpassClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"elements": []}
    with patch.object(OSM_OVERPASS_LIMITER, "call_with_retry", return_value=mock_resp):
        assert client.discover({}) == []


def test_discover_non_200_returns_empty() -> None:
    client = OsmOverpassClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch.object(OSM_OVERPASS_LIMITER, "call_with_retry", return_value=mock_resp):
        assert client.discover({}) == []


def test_osm_limiter_is_source_limiter() -> None:
    assert isinstance(OSM_OVERPASS_LIMITER, SourceLimiter)


def test_osm_and_reconciler_import_chain_no_cycle() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(repo_root)!r})\n"
        "from app.contrib.osm_overpass_client import OsmOverpassClient  # noqa: F401\n"
        "from app.contrib.ingest_reconciler import reconcile_hit  # noqa: F401\n"
        "import json\n"
        "print(json.dumps({\n"
        '  "models_loaded": "app.db.models" in sys.modules,\n'
        "}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
        env={**os.environ, "AUTH_DEV_MODE": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["models_loaded"] is False


def test_osm_client_sends_descriptive_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_ua: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_ua.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, json={"elements": []})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        merged = dict(kwargs)
        merged["transport"] = transport
        return real_client(*args, **merged)

    monkeypatch.setattr("app.contrib.osm_overpass_client.httpx.Client", client_factory)
    with patch.object(OSM_OVERPASS_LIMITER, "call_with_retry", lambda fn: fn()):
        OsmOverpassClient().discover({"tag": "leisure", "value": "marina"})
    assert len(captured_ua) == 1
    assert captured_ua[0] == OSM_OVERPASS_USER_AGENT
    assert not captured_ua[0].lower().startswith("python-httpx")


def test_osm_client_logs_warning_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(406, text="not acceptable")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        merged = dict(kwargs)
        merged["transport"] = transport
        return real_client(*args, **merged)

    monkeypatch.setattr("app.contrib.osm_overpass_client.httpx.Client", client_factory)
    import app.contrib.osm_overpass_client as oc

    with patch.object(oc.logger, "warning") as mock_warn:
        with patch.object(OSM_OVERPASS_LIMITER, "call_with_retry", lambda fn: fn()):
            hits = OsmOverpassClient().discover({"tag": "leisure", "value": "marina"})
    assert hits == []
    mock_warn.assert_called()
    args = mock_warn.call_args[0]
    template, *values = args
    rendered = template % tuple(values) if values else template
    assert "status=406" in rendered
    assert "leisure" in rendered and "marina" in rendered


def test_osm_client_json_parse_error_logs_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{not valid json")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        merged = dict(kwargs)
        merged["transport"] = transport
        return real_client(*args, **merged)

    monkeypatch.setattr("app.contrib.osm_overpass_client.httpx.Client", client_factory)
    import app.contrib.osm_overpass_client as oc

    with patch.object(oc.logger, "warning") as mock_warn:
        with patch.object(OSM_OVERPASS_LIMITER, "call_with_retry", lambda fn: fn()):
            hits = OsmOverpassClient().discover({"tag": "leisure", "value": "marina"})
    assert hits == []
    mock_warn.assert_called()
    args = mock_warn.call_args[0]
    template, *values = args
    rendered = template % tuple(values) if values else template
    assert "json_parse_error" in rendered
    assert "leisure" in rendered and "marina" in rendered


def test_osm_client_transport_error_logs_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated", request=_request)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        merged = dict(kwargs)
        merged["transport"] = transport
        return real_client(*args, **merged)

    monkeypatch.setattr("app.contrib.osm_overpass_client.httpx.Client", client_factory)
    import app.contrib.osm_overpass_client as oc

    with patch.object(oc.logger, "warning") as mock_warn:
        with patch.object(OSM_OVERPASS_LIMITER, "call_with_retry", lambda fn: fn()):
            hits = OsmOverpassClient().discover({"tag": "leisure", "value": "dog_park"})
    assert hits == []
    mock_warn.assert_called()
    args = mock_warn.call_args[0]
    template, *values = args
    rendered = template % tuple(values) if values else template
    assert "transport_error" in rendered
    assert "leisure" in rendered and "dog_park" in rendered
