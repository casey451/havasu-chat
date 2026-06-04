"""ABC15 Lake Havasu RSS parsing (source-expansion #8). No live HTTP."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contrib import abc15_havasu
from app.contrib.civicplus_rss import parse_feed

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "abc15"


def _rss() -> str:
    return (FIXTURES / "lake_havasu.rss").read_text(encoding="utf-8")


def test_parse_feed_for_abc15() -> None:
    items = parse_feed(_rss(), source=abc15_havasu.SOURCE)
    assert len(items) == 2
    first = items[0]
    assert first.source == "abc15_havasu"
    assert first.title == "Crews battle brush fire near Lake Havasu City"
    assert first.url.endswith("/brush-fire")
    assert first.published_at is not None and first.published_at.year == 2026


def test_cli_dry_run(monkeypatch, capsys) -> None:
    import scripts.abc15_pull as cli

    monkeypatch.setattr(
        cli.abc15_havasu, "fetch_articles", lambda **_: parse_feed(_rss(), source="abc15_havasu")
    )
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "abc15_havasu — DRY RUN" in out
    assert "would-insert:   2" in out


def test_cli_apply_guarded() -> None:
    import scripts.abc15_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply"])
    assert exc.value.code == 2
