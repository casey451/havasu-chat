"""Phase 5.2 — regression tests for scripts.osm_overpass_pull JSONL writer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.contrib.ingest_base import RawHit
from scripts import osm_overpass_load
from scripts import osm_overpass_pull as pull


def _marina_elements() -> list[dict]:
    return [
        {
            "type": "node",
            "id": 1001,
            "lat": 34.5,
            "lon": -114.35,
            "tags": {"name": "Marina One", "leisure": "marina"},
        },
        {
            "type": "node",
            "id": 1002,
            "lat": 34.51,
            "lon": -114.36,
            "tags": {"name": "Marina Two", "leisure": "marina"},
        },
        {
            "type": "node",
            "id": 1003,
            "lat": 34.52,
            "lon": -114.37,
            "tags": {"name": "Marina Three", "leisure": "marina"},
        },
    ]


def _hits_from_elements(elements: list[dict]) -> list[RawHit]:
    out: list[RawHit] = []
    for el in elements:
        tags = el.get("tags") or {}
        out.append(
            RawHit(
                source="osm",
                source_stable_id=f"osm_{el['type']}_{el['id']}",
                name=str(tags["name"]),
                lat=float(el["lat"]),
                lng=float(el["lon"]),
                raw={"element": el, "tags": tags},
            )
        )
    return out


MARINA_HITS = _hits_from_elements(_marina_elements())


@pytest.fixture
def mock_marina_discover(monkeypatch: pytest.MonkeyPatch) -> None:
    def _discover(
        self: pull.OsmOverpassClient, _query: dict[str, object]
    ) -> list[RawHit]:
        return list(MARINA_HITS)

    monkeypatch.setattr(pull.OsmOverpassClient, "discover", _discover)


def test_pull_writes_wrapper_line_jsonl_to_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_marina_discover: None
) -> None:
    default_out = tmp_path / "osm_elements.jsonl"
    monkeypatch.setattr(pull, "DEFAULT_OUTPUT_PATH", default_out)
    monkeypatch.setattr(
        sys,
        "argv",
        ["osm_overpass_pull", "--tag", "leisure", "--value", "marina"],
    )
    assert pull.main() == 0
    assert default_out.is_file()
    lines = [ln for ln in default_out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert list(obj.keys()) == ["elements"]
    assert len(obj["elements"]) == 3
    names = {el["tags"]["name"] for el in obj["elements"]}
    assert names == {"Marina One", "Marina Two", "Marina Three"}


def test_pull_dry_run_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_marina_discover: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    default_out = tmp_path / "osm_elements.jsonl"
    monkeypatch.setattr(pull, "DEFAULT_OUTPUT_PATH", default_out)
    monkeypatch.setattr(
        sys,
        "argv",
        ["osm_overpass_pull", "--tag", "leisure", "--value", "marina", "--dry-run"],
    )
    assert pull.main() == 0
    assert not default_out.exists()
    out = capsys.readouterr().out
    assert "dry-run: no JSONL written" in out
    assert "Discovered 3" in out


def test_pull_output_flag_writes_to_explicit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_marina_discover: None
) -> None:
    default_out = tmp_path / "default_osm_elements.jsonl"
    explicit = tmp_path / "marinas.jsonl"
    monkeypatch.setattr(pull, "DEFAULT_OUTPUT_PATH", default_out)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "osm_overpass_pull",
            "--tag",
            "leisure",
            "--value",
            "marina",
            "--output",
            str(explicit),
        ],
    )
    assert pull.main() == 0
    assert explicit.is_file()
    assert not default_out.exists()


def test_pull_output_is_consumable_by_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_marina_discover: None
) -> None:
    out_path = tmp_path / "chain.jsonl"
    monkeypatch.setattr(pull, "DEFAULT_OUTPUT_PATH", out_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["osm_overpass_pull", "--tag", "leisure", "--value", "marina"],
    )
    assert pull.main() == 0
    obj = json.loads(out_path.read_text(encoding="utf-8").strip().splitlines()[0])
    yielded = list(
        osm_overpass_load._iter_feature_elements(
            obj, tag="leisure", value="marina"
        )
    )
    assert len(yielded) == 3
    for el in yielded:
        assert el["tags"].get("leisure") == "marina"
