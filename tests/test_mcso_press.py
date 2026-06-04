"""MCSO press-release parsing (source-expansion #5). No live HTTP — fixture HTML."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contrib import mcso_press

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mcso"


def _html() -> str:
    return (FIXTURES / "press_list.html").read_text(encoding="utf-8")


def test_parse_press_releases() -> None:
    items = mcso_press.parse_press_releases(_html())
    # The anchorless placeholder article is skipped.
    assert len(items) == 2
    first = items[0]
    assert first.source == "mcso_press"
    assert first.title == "Deputies Rescue Two Boaters Near Topock Gorge"
    # Relative href resolved against the listing URL.
    assert first.url.startswith("https://www.mohave.gov/")
    assert first.published_at is not None
    assert first.published_at.month == 6
    assert first.summary and "Topock" in first.summary


def test_cli_dry_run(monkeypatch, capsys) -> None:
    import scripts.mcso_press_pull as cli

    monkeypatch.setattr(
        cli.mcso_press, "fetch_press_releases", lambda **_: mcso_press.parse_press_releases(_html())
    )
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "mcso_press — DRY RUN" in out
    assert "would-insert:   2" in out


def test_cli_apply_guarded() -> None:
    import scripts.mcso_press_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply"])
    assert exc.value.code == 2
