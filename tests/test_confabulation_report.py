from __future__ import annotations

import csv
from pathlib import Path

from app.eval.confabulation_report import write_per_row_csv, write_summary_md
from scripts.confabulation_eval import _anchor_names_from_file


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


def test_confabulation_report_excludes_tier_chat(tmp_path: Path) -> None:
    out = tmp_path / "summary.md"
    runs = [
        {
            "row_id": "r_chat",
            "row_name": "Chat Row",
            "flag_state": "off",
            "tier_used": "chat",
            "gating_hit_count": 0,
            "advisory_hit_count": 0,
            "hit_count": 0,
            "gating_tokens": [],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [],
            "excluded_from_summary": True,
            "excluded_reason": "tier_chat_no_formatter",
        },
        {
            "row_id": "r2",
            "row_name": "Row Two",
            "flag_state": "off",
            "tier_used": "2",
            "gating_hit_count": 1,
            "advisory_hit_count": 0,
            "hit_count": 1,
            "gating_tokens": ["private"],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [{"token": "private", "layer": "2", "row_ids_in_scope": ()}],
            "excluded_from_summary": False,
        },
    ]
    write_summary_md(out, runs)
    text = out.read_text(encoding="utf-8")
    assert "Included in gating-confabulation-rate summary: 1" in text
    assert "Excluded from gating confabulation-rate summary: 1" in text
    assert "`off`: 1/1 (100.0%) with ≥1 gating hit" in text


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
            "category": "swim",
            "activity_category": None,
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
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == [
        "row_id",
        "row_name",
        "category",
        "activity_category",
        "total_runs",
        "included_runs",
        "gating_runs_with_hit",
        "advisory_token_count",
        "top_3_gating_tokens",
    ]
    data = rows[1]
    assert data[0] == "id1" and data[1] == "N"
    assert data[2] == "swim"
    assert data[3] == ""
    assert data[4] == "1"  # total
    assert data[5] == "1"  # included
    assert data[6] == "1"  # gating with hit
    assert data[7] == "2"  # advisory count


def test_per_row_csv_provider_vs_program_category_columns(tmp_path: Path) -> None:
    """Provider rows emit category; Program rows emit activity_category (inverse empty)."""
    p = tmp_path / "mix.csv"
    runs = [
        {
            "row_id": "prov1",
            "row_name": "Swim Co",
            "category": "swim",
            "activity_category": None,
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
        {
            "row_id": "prog1",
            "row_name": "Arts Venue",
            "category": None,
            "activity_category": "arts",
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
    write_per_row_csv(p, runs)
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    by_name = {r[1]: r for r in rows[1:]}
    assert by_name["Swim Co"][2] == "swim" and by_name["Swim Co"][3] == ""
    assert by_name["Arts Venue"][2] == "" and by_name["Arts Venue"][3] == "arts"


def test_per_row_csv_mixed_runs_grouped_counts(tmp_path: Path) -> None:
    """Same (row_id, row_name) aggregates counts across flag states like v1."""
    p = tmp_path / "g.csv"
    base = {
        "row_id": "same",
        "row_name": "Grouped Row",
        "category": "fitness",
        "activity_category": None,
        "tier_used": "2",
        "advisory_hit_count": 0,
        "hit_count": 1,
        "gating_tokens": ["t"],
        "layer_1_advisory_tokens": [],
        "layer_2_hits": [{"token": "t", "layer": "2", "row_ids_in_scope": ()}],
        "excluded_from_summary": False,
    }
    runs = [
        {**base, "flag_state": "off", "gating_hit_count": 1},
        {**base, "flag_state": "on", "gating_hit_count": 0, "gating_tokens": [], "layer_2_hits": []},
    ]
    write_per_row_csv(p, runs)
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    data = rows[1]
    assert data[4] == "2"  # total_runs
    assert data[5] == "2"  # included_runs
    assert data[6] == "1"  # gating_runs_with_hit (one included run with ≥1 gating hit)


def test_write_summary_md_default_regression_anchors(tmp_path: Path) -> None:
    out = tmp_path / "s.md"
    runs = [
        {
            "row_id": "a",
            "row_name": "Aqua Beginnings",
            "flag_state": "off",
            "tier_used": "2",
            "gating_hit_count": 0,
            "advisory_hit_count": 0,
            "hit_count": 0,
            "gating_tokens": [],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [],
            "excluded_from_summary": False,
        }
    ]
    write_summary_md(out, runs, anchors=None)
    text = out.read_text(encoding="utf-8")
    assert "- `Aqua Beginnings`: 0/1 included runs with ≥1 gating hit" in text
    assert "- `Grace Arts Live`: 0/0 included runs with ≥1 gating hit" in text


def test_write_summary_md_custom_regression_anchors(tmp_path: Path) -> None:
    out = tmp_path / "s2.md"
    runs = [
        {
            "row_id": "x",
            "row_name": "Foo Provider",
            "flag_state": "off",
            "tier_used": "2",
            "gating_hit_count": 1,
            "advisory_hit_count": 0,
            "hit_count": 1,
            "gating_tokens": ["z"],
            "layer_1_advisory_tokens": [],
            "layer_2_hits": [{"token": "z", "layer": "2", "row_ids_in_scope": ()}],
            "excluded_from_summary": False,
        }
    ]
    write_summary_md(out, runs, anchors=("Foo Provider", "Bar Program"))
    text = out.read_text(encoding="utf-8")
    assert "- `Foo Provider`: 1/1 included runs with ≥1 gating hit" in text
    assert "- `Bar Program`: 0/0 included runs with ≥1 gating hit" in text
    assert "Aqua Beginnings" not in text


def test_anchor_names_from_file_skips_comments_and_blanks(tmp_path: Path) -> None:
    f = tmp_path / "anchors.txt"
    f.write_text(
        "\n# ignored\n\nFoo Bar\n  Baz Qux  \n",
        encoding="utf-8",
    )
    assert _anchor_names_from_file(f) == ("Foo Bar", "Baz Qux")
