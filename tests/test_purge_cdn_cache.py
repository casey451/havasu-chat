"""Unit tests for the CDN cache-purge tool — the safety no-op and the deploy-SHA
match. The live Cloudflare call isn't exercised (no network / no creds in CI)."""

from __future__ import annotations

import pytest

from scripts import purge_cdn_cache as pc


def test_main_is_a_noop_without_creds(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    # The critical safety property: with no CF creds it NEVER fails a deploy/data op.
    monkeypatch.delenv("CF_PURGE_API_TOKEN", raising=False)
    monkeypatch.delenv("CF_ZONE_ID", raising=False)
    assert pc.main([]) == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_wait_for_deploy_matches_short_or_full_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "_get_json", lambda url, **kw: {"build_sha": "abc123def456"})
    # Full 40-char SHA vs the 12-char meta/health prefix → still a match.
    assert pc.wait_for_deploy("https://x", "abc123def456789abc", timeout_s=5, interval_s=0) is True


def test_wait_for_deploy_times_out_on_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "_get_json", lambda url, **kw: {"build_sha": "oldsha000000"})
    assert pc.wait_for_deploy("https://x", "newsha111111", timeout_s=0, interval_s=0) is False
