"""Unit tests for scripts/post_deploy_smoke.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml

from app.chat.halt3_validator import EvalQuerySpec
from scripts import post_deploy_smoke as smoke


def _sample_yaml(rows: int) -> str:
    return yaml.safe_dump(
        [
            {
                "id": f"q{i:02d}",
                "query": f"query {i}",
                "expected_tier": "tier2",
                "expected_disclosure_path": "cited",
                "expected_confabulation_rate": 0.0,
            }
            for i in range(1, rows + 1)
        ]
    )


def test_load_smoke_queries_returns_23_from_30_row_yaml(tmp_path: Path) -> None:
    path = tmp_path / "eval.yaml"
    path.write_text(_sample_yaml(30), encoding="utf-8")
    specs = smoke.load_smoke_queries(path, limit=23)
    assert len(specs) == 23
    assert specs[0].id == "q01"
    assert specs[-1].id == "q23"


def test_load_smoke_queries_limit_5(tmp_path: Path) -> None:
    path = tmp_path / "eval.yaml"
    path.write_text(_sample_yaml(30), encoding="utf-8")
    specs = smoke.load_smoke_queries(path, limit=5)
    assert len(specs) == 5
    assert specs[-1].id == "q05"


def test_evaluate_matching_tier() -> None:
    spec = EvalQuerySpec("q01", "hello", "tier2", "cited", 0.0)
    passed, failures = smoke.evaluate(spec, {"tier_used": "2"})
    assert passed is True
    assert failures == []


def test_evaluate_mismatched_tier() -> None:
    spec = EvalQuerySpec("q01", "hello", "tier2", "cited", 0.0)
    passed, failures = smoke.evaluate(spec, {"tier_used": "3"})
    assert passed is False
    assert failures and "tier expected" in failures[0]


def test_evaluate_list_expected_tier() -> None:
    spec = EvalQuerySpec("q02", "hello", ["tier2", "tier3"], "cited", 0.0)
    assert smoke.evaluate(spec, {"tier_used": "3"})[0] is True
    assert smoke.evaluate(spec, {"tier_used": "2"})[0] is True
    assert smoke.evaluate(spec, {"tier_used": "chat"})[0] is False


def test_run_one_against_mock_server() -> None:
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"tier_used": "2", "response": "ok"}

    class _FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, json: dict) -> _FakeResponse:
            assert url == "https://example.test/api/chat"
            assert json["query"] == "hello"
            assert json["session_id"].startswith("smoke-")
            return _FakeResponse()

    with patch.object(httpx, "Client", _FakeClient):
        body = smoke.run_one("hello", "https://example.test", timeout=5.0)
    assert body["tier_used"] == "2"


def test_main_writes_json_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(_sample_yaml(2), encoding="utf-8")
    out_path = tmp_path / "smoke_result.json"

    def _fake_run_one(query: str, url: str, timeout: float = 30.0) -> dict:
        return {"tier_used": "2"}

    monkeypatch.setattr(smoke, "run_one", _fake_run_one)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_deploy_smoke.py",
            "--url",
            "https://example.test",
            "--eval-set",
            str(eval_path),
            "--limit",
            "2",
            "--json-out",
            str(out_path),
        ],
    )
    assert smoke.main() == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["total"] == 2
    assert data["passed"] == 2
    assert len(data["results"]) == 2


def test_main_returns_exit_code_1_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(_sample_yaml(1), encoding="utf-8")

    def _bad_run_one(query: str, url: str, timeout: float = 30.0) -> dict:
        return {"tier_used": "chat"}

    monkeypatch.setattr(smoke, "run_one", _bad_run_one)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_deploy_smoke.py",
            "--url",
            "https://example.test",
            "--eval-set",
            str(eval_path),
            "--limit",
            "1",
        ],
    )
    assert smoke.main() == 1
