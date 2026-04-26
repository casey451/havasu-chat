from __future__ import annotations

from pathlib import Path

from app.eval.confabulation_report import write_per_row_csv, write_summary_md


def test_summary_excludes_tier1_from_gating_rate(tmp_path: Path) -> None:
    out = tmp_path / "summary.md"
    runs = [
        {
            "row_id": "r1",
            "row_name": "Row One",
            "flag_state": "off",
            "tier_used": "1",
            "gating_hit_count": 0,
            "advisory_hit_count": 0,
            "hit_count": 0,
            "gating_tokens": [],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [],
            "excluded_from_summary": True,
        },
        {
            "row_id": "r1",
            "row_name": "Row One",
            "flag_state": "off",
            "tier_used": "2",
            "gating_hit_count": 0,
            "advisory_hit_count": 0,
            "hit_count": 0,
            "gating_tokens": [],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [],
            "excluded_from_summary": False,
        },
    ]
    write_summary_md(out, runs)
    text = out.read_text(encoding="utf-8")
    assert "Included in gating-confabulation-rate summary: 1" in text
    assert "Excluded from gating confabulation-rate summary: 1" in text
    assert "`off`: 0/1 (0.0%) with ≥1 gating hit" in text
    assert "Tier 1 invocations excluded: 1" in text
    assert "Tier 3 invocations excluded (no Layer 2 gating signal): 0" in text


def test_summary_excludes_tier3_from_gating_rate(tmp_path: Path) -> None:
    out = tmp_path / "summary.md"
    runs = [
        {
            "row_id": "r2",
            "row_name": "Row Two",
            "flag_state": "on",
            "tier_used": "3",
            "gating_hit_count": 0,
            "advisory_hit_count": 0,
            "hit_count": 0,
            "gating_tokens": [],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [],
            "excluded_from_summary": True,
        },
        {
            "row_id": "r2",
            "row_name": "Row Two",
            "flag_state": "on",
            "tier_used": "2",
            "gating_hit_count": 1,
            "advisory_hit_count": 0,
            "hit_count": 1,
            "gating_tokens": ["outdoor"],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [{"token": "outdoor", "layer": "2", "row_ids_in_scope": ()}],
            "excluded_from_summary": False,
        },
    ]
    write_summary_md(out, runs)
    text = out.read_text(encoding="utf-8")
    assert "Included in gating-confabulation-rate summary: 1" in text
    assert "Excluded from gating confabulation-rate summary: 1" in text
    assert "Tier 3 invocations excluded (no Layer 2 gating signal): 1" in text
    assert "`on`: 1/1 (100.0%) with ≥1 gating hit" in text
    assert "`outdoor`: 1" in text  # gating top tokens


def test_tier3_with_layer2_included_in_summary(tmp_path: Path) -> None:
    out = tmp_path / "summary.md"
    runs = [
        {
            "row_id": "r3",
            "row_name": "Tier3 Row",
            "flag_state": "off",
            "tier_used": "3",
            "gating_hit_count": 1,
            "advisory_hit_count": 0,
            "hit_count": 1,
            "gating_tokens": ["private"],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [{"token": "private", "layer": "2", "row_ids_in_scope": ()}],
            "excluded_from_summary": False,
        }
    ]
    write_summary_md(out, runs)
    text = out.read_text(encoding="utf-8")
    assert "Included in gating-confabulation-rate summary: 1" in text
    assert "Tier 3 invocations **included** due to Layer 2 hits: 1" in text
    assert "Tier 3 invocations excluded (no Layer 2 gating signal): 0" in text


def test_report_layer1_advisory_split(tmp_path: Path) -> None:
    out = tmp_path / "summary.md"
    runs = [
        {
            "row_id": "r1",
            "row_name": "A",
            "flag_state": "off",
            "tier_used": "2",
            "gating_hit_count": 1,
            "advisory_hit_count": 1,
            "hit_count": 1,
            "gating_tokens": ["heated"],
            "layer_1_advisory_tokens": ["scaffold"],
            "layer_2_hits": [{"token": "heated", "layer": "2", "row_ids_in_scope": ()}],
            "excluded_from_summary": False,
        }
    ]
    write_summary_md(out, runs)
    text = out.read_text(encoding="utf-8")
    assert "## Top gating confabulation tokens" in text
    assert "`heated`: 1" in text
    assert "## Layer 1 candidate tokens (advisory" in text
    assert "do not gate" in text.lower() or "do not gate the headline" in text
    assert "`scaffold`: 1" in text
    assert text.index("## Top gating") < text.index("## Layer 1")


def test_per_row_csv_gating_columns(tmp_path: Path) -> None:
    p = tmp_path / "p.csv"
    runs = [
        {
            "row_id": "id1",
            "row_name": "N",
            "flag_state": "off",
            "tier_used": "2",
            "gating_hit_count": 1,
            "advisory_hit_count": 2,
            "hit_count": 1,
            "gating_tokens": ["a", "a"],
            "layer_1_advisory_tokens": ["b", "c"],
            "layer_2_hits": [{"token": "a", "layer": "2", "row_ids_in_scope": ()}],
            "excluded_from_summary": False,
        }
    ]
    write_per_row_csv(p, runs)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("row_id,row_name,total_runs,included_runs,gating_runs_with_hit")
    data = lines[1].split(",")
    assert data[0] == "id1" and data[1] == "N"
    assert data[2] == "1"  # total
    assert data[3] == "1"  # included
    assert data[4] == "1"  # gating with hit
    assert data[5] == "2"  # advisory count
