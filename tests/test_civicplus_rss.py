"""CivicPlus RSS parsing — lhc_newsflash + lhc_alerts (source-expansion #1, #2).

No live HTTP: parsing is exercised against a recorded fixture; the CLI dry-run
is exercised with the fetch monkeypatched. Verifies normalisation to NewsItem,
malformed-item skipping, and the empty-feed (Alert Center) steady state.
"""

from __future__ import annotations

from pathlib import Path

from app.contrib import civicplus_rss
from app.contrib.scrape_dryrun import summarize

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "civicplus"


def _newsflash_text() -> str:
    return (FIXTURES / "newsflash.xml").read_text(encoding="utf-8")


def test_parse_feed_normalises_items() -> None:
    items = civicplus_rss.parse_feed(_newsflash_text(), source="lhc_newsflash")
    # The malformed (empty-title) item is skipped.
    assert len(items) == 2
    first = items[0]
    assert first.source == "lhc_newsflash"
    assert first.title == "Mesquite Avenue Lane Closure June 9-13"
    assert first.url == "https://www.lhcaz.gov/CivicAlerts.aspx?AID=1234"
    assert first.published_at is not None
    assert first.published_at.year == 2026
    assert "Public Works" in first.categories
    assert first.summary and "Mesquite" in first.summary


def test_parse_feed_dedupe_key_is_url() -> None:
    items = civicplus_rss.parse_feed(_newsflash_text(), source="lhc_newsflash")
    assert items[0].dedupe_key() == "https://www.lhcaz.gov/civicalerts.aspx?aid=1234"


def test_empty_feed_is_healthy() -> None:
    """Alert Center is usually empty — parsing an empty channel yields []."""
    empty = '<?xml version="1.0"?><rss version="2.0"><channel><title>Alerts</title></channel></rss>'
    items = civicplus_rss.parse_feed(empty, source="lhc_alerts")
    assert items == []
    counts = summarize(items)
    assert counts.fetched == 0


def test_cli_dry_run_reports(monkeypatch, capsys) -> None:
    import scripts.lhc_civicplus_pull as cli

    items = civicplus_rss.parse_feed(_newsflash_text(), source="lhc_newsflash")
    monkeypatch.setattr(cli.lhc_newsflash, "fetch_newsflash", lambda **_: items)
    rc = cli.main(["--feed", "newsflash"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "lhc_newsflash — DRY RUN" in out
    assert "would-insert:   2" in out


def test_cli_apply_is_guarded(monkeypatch) -> None:
    import pytest

    import scripts.lhc_civicplus_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply"])
    assert exc.value.code == 2
