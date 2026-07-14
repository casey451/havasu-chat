"""Unit tests for the id-parsing in scripts/quarantine_events_by_id.py.

The DB-touching path (guard on status=="live", the undo round-trip) is exercised
by the gated quarantine-events-apply workflow's dry-run against prod; here we pin
the pure ``--ids`` parsing that decides which rows get touched.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "quarantine_events_by_id",
    Path(__file__).resolve().parents[1] / "scripts" / "quarantine_events_by_id.py",
)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)


def test_parse_ids_splits_comma_and_space() -> None:
    assert _MOD._parse_ids(["a b,c"]) == ["a", "b", "c"]


def test_parse_ids_flattens_repeated_and_dedupes_preserving_order() -> None:
    assert _MOD._parse_ids(["id1 id2", "id2,id3"]) == ["id1", "id2", "id3"]


def test_parse_ids_empty_and_none() -> None:
    assert _MOD._parse_ids(None) == []
    assert _MOD._parse_ids([""]) == []
    assert _MOD._parse_ids(["  ,  "]) == []
