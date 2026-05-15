"""Unit tests for :mod:`app.contrib.az_roc_client` HTML parsing / match rules (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contrib.az_roc_client import _parse_results_table, pick_best_az_roc_row

FIXTURE_HTML = Path(__file__).resolve().parent / "fixtures" / "az_roc_results_sample.html"


@pytest.fixture
def az_roc_fixture_html() -> str:
    return FIXTURE_HTML.read_text(encoding="utf-8")


def test_parse_single_license_row(az_roc_fixture_html: str) -> None:
    rows = _parse_results_table(az_roc_fixture_html)
    solo = next(r for r in rows if r["license_number"] == "ROC 111111")
    assert solo["business_name"] == "Solo Electric Inc"
    assert solo["classification"] == "CR-11 Electrical Work"
    assert solo["status"] == "ACTIVE"
    assert solo["qualifying_party"] == "Pat Lee"
    assert "Flagstaff" in (solo.get("address") or "")


def test_parse_rowspan_second_license_inherits_business(az_roc_fixture_html: str) -> None:
    rows = _parse_results_table(az_roc_fixture_html)
    by_lic = {r["license_number"]: r for r in rows}
    r1 = by_lic["ROC 222222"]
    r2 = by_lic["ROC 222223"]
    blob = "Dual Trade LLC\nDBA : Dual Trade Shop"
    assert r1["business_name"] == blob
    assert r2["business_name"] == blob
    assert r1["classification"] == "CR-11 Electrical"
    assert r2["classification"] == "CR-8 Windows"
    assert r2["address"] == "Phoenix, AZ, 85001"
    assert r2["phone"] == "(602)555-0202"


def test_parse_skips_separator_line_rows(az_roc_fixture_html: str) -> None:
    rows = _parse_results_table(az_roc_fixture_html)
    assert len(rows) == 3
    assert all(r["license_number"] for r in rows)


def test_parse_empty_tbody_returns_empty_list() -> None:
    html = "<table><tbody></tbody></table>"
    assert _parse_results_table(html) == []


def test_pick_best_exact_business_name(az_roc_fixture_html: str) -> None:
    rows = _parse_results_table(az_roc_fixture_html)
    choice = pick_best_az_roc_row(rows, "Dual Trade Shop")
    assert choice is not None
    assert choice["license_number"] == "ROC 222222"


def test_pick_best_prefers_active_when_no_name_match() -> None:
    rows = [
        {
            "business_name": "Other Co",
            "license_number": "ROC 999998",
            "classification": None,
            "status": "SUSPENDED",
        },
        {
            "business_name": "Active Co",
            "license_number": "ROC 999999",
            "classification": None,
            "status": "ACTIVE",
        },
    ]
    picked = pick_best_az_roc_row(rows, "__no_matching_name__")
    assert picked["license_number"] == "ROC 999999"


def test_pick_best_first_row_when_no_match_and_no_active() -> None:
    rows = [
        {
            "business_name": "X",
            "license_number": "ROC 1",
            "classification": None,
            "status": "EXPIRED",
        },
        {
            "business_name": "Y",
            "license_number": "ROC 2",
            "classification": None,
            "status": "SUSPENDED",
        },
    ]
    assert pick_best_az_roc_row(rows, "")["license_number"] == "ROC 1"


def test_pick_best_empty_rows_is_none() -> None:
    assert pick_best_az_roc_row([], "anything") is None
