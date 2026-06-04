"""News-Herald sitemap + lede parsing (source-expansion #6). No live HTTP."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contrib import news_herald

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "news_herald"


def test_parse_news_sitemap() -> None:
    xml = (FIXTURES / "news.xml").read_text(encoding="utf-8")
    items = news_herald.parse_news_sitemap(xml)
    # The title-less third URL is skipped.
    assert len(items) == 2
    first = items[0]
    assert first.source == "news_herald"
    assert first.title == "Council approves $120M budget for fiscal 2027"
    assert first.url.endswith("article_001.html")
    assert first.published_at is not None and first.published_at.year == 2026
    assert "city council" in first.keywords
    assert "budget" in first.keywords


def test_extract_lede_is_free_paragraphs_only() -> None:
    """Rule 6: only the first ~2 visible paragraphs; the encoded tail is never read."""
    html = (FIXTURES / "article.html").read_text(encoding="utf-8")
    lede = news_herald.extract_lede(html, max_paragraphs=2)
    assert lede is not None
    assert "$120 million budget" in lede
    assert "stormwater fee" in lede
    # The ROT47-obfuscated paywall tail must NOT appear in the lede.
    assert "@C6 E96" not in lede
    assert "do not decode" not in lede


def test_cli_dry_run(monkeypatch, capsys) -> None:
    import scripts.news_herald_pull as cli

    xml = (FIXTURES / "news.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(
        cli.news_herald, "fetch_news_sitemap", lambda **_: news_herald.parse_news_sitemap(xml)
    )
    assert cli.main(["--feed", "news"]) == 0
    out = capsys.readouterr().out
    assert "news_herald:news — DRY RUN" in out
    assert "would-insert:   2" in out


def test_cli_apply_guarded() -> None:
    import scripts.news_herald_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply"])
    assert exc.value.code == 2
