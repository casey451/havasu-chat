"""Tests for ``scripts/confabulation_eval.py`` (imported via importlib — not a package)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.eval.confabulation_query_gen import Probe, normalize_row_name_for_include


@pytest.fixture(scope="module")
def confabulation_eval_mod():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "confabulation_eval.py"
    spec = importlib.util.spec_from_file_location("confabulation_eval_script", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_select_probes_include_ascii_hyphen_matches_catalog_en_dash_title(
    confabulation_eval_mod,
) -> None:
    mod = confabulation_eval_mod
    probes = [
        Probe("tell me about X", "rid1", "program", "program_tell_me_about"),
    ]
    name_map = {"rid1": "Open Jump \u2013 90 Minutes"}
    include = {normalize_row_name_for_include("Open Jump - 90 Minutes")}
    out = mod._select_probes(
        probes,
        rows_mode="both",
        include=include,
        exclude=set(),
        limit=None,
        name_map=name_map,
    )
    assert len(out) == 1 and out[0].row_id == "rid1"


def test_select_probes_exclude_normalized(confabulation_eval_mod) -> None:
    mod = confabulation_eval_mod
    probes = [Probe("q", "r1", "program", "t")]
    name_map = {"r1": "Open Jump \u2013 90 Minutes"}
    exclude = {normalize_row_name_for_include("Open Jump - 90 Minutes")}
    out = mod._select_probes(
        probes, rows_mode="both", include=set(), exclude=exclude, limit=None, name_map=name_map
    )
    assert out == []


def test_enrich_for_reports_excludes_tier_chat(confabulation_eval_mod) -> None:
    mod = confabulation_eval_mod
    records = [
        {
            "probe": {
                "query_text": "outside scope question",
                "template_id": "provider_tell_me_about",
                "row_id": "r_chat",
                "row_type": "provider",
            },
            "flag_state": "off",
            "response_text": "That's outside what I cover right now.",
            "evidence_row_dicts": [],
            "tier_used": "chat",
            "latency_ms": 900,
            "raw_log": {},
            "error": None,
            "hits": [],
            "run_index": 0,
        }
    ]
    name_map = {"r_chat": "Chat Tier Row"}
    enriched = mod._enrich_for_reports(records, name_map)
    assert len(enriched) == 1
    assert enriched[0]["tier_used"] == "chat"
    assert enriched[0]["excluded_from_summary"] is True
    assert enriched[0]["excluded_reason"] == "tier_chat_no_formatter"
