"""Phase 9 — the nightly integrity report's pure pieces.

The report itself runs against prod via .github/workflows/directory-integrity
.yml; this pins the helpers and the baseline-file contract so a refactor can't
silently change what "regression" means.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "integrity_report", _ROOT / "scripts" / "integrity_report.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_phone_normalization_and_ignore_list():
    mod = _load_module()
    assert mod._norm_phone("(928) 453-4600") == "9284534600"
    assert mod._norm_phone("+1 928-453-4600") == "9284534600"
    assert mod._norm_phone(None) == ""
    assert mod._norm_phone("453-4600") == ""  # short numbers never cluster
    # The CVB shared 800 number is a known placeholder-contact class, not a dup.
    assert "8002428278" in mod._IGNORED_PHONES


def test_baseline_file_shape():
    base_path = _ROOT / "scripts" / "integrity_baseline.json"
    assert base_path.exists(), "baseline must ship with the workflow"
    data = json.loads(base_path.read_text(encoding="utf-8"))
    for key in ("zero_leaf_providers", "zero_contact_providers",
                "same_phone_clusters", "past_live_oneoffs"):
        assert key in data and isinstance(data[key], int), key
