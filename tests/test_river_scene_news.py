"""RiverScene WP REST news parsing (source-expansion #7). No live HTTP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contrib import river_scene_news

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "river_scene"


def _posts() -> list[dict]:
    return json.loads((FIXTURES / "wp_posts.json").read_text(encoding="utf-8"))


def test_parse_posts() -> None:
    items = river_scene_news.parse_posts(_posts())
    # The link-less malformed post is skipped.
    assert len(items) == 2
    first = items[0]
    assert first.source == "river_scene_news"
    # HTML entities decoded, tags stripped.
    assert first.title == "New Brewery Opens Downtown – Grand Opening Saturday"
    assert first.url.endswith("/new-brewery-opens-downtown/")
    assert first.published_at is not None and first.published_at.year == 2026
    assert first.summary and "craft brewery" in first.summary
    assert "12" in first.categories


def test_cli_dry_run(monkeypatch, capsys) -> None:
    import scripts.river_scene_news_pull as cli

    monkeypatch.setattr(
        cli.river_scene_news, "fetch_posts", lambda **_: river_scene_news.parse_posts(_posts())
    )
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "river_scene_news — DRY RUN" in out
    assert "would-insert:   2" in out


def test_cli_apply_guarded() -> None:
    import scripts.river_scene_news_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply"])
    assert exc.value.code == 2
