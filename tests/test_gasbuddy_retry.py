"""fetch_lhc_stations retries the WHOLE pull on a fresh client when a pass
returns zero stations (the Cloudflare-challenge signature that caused
gas-prices #131), and never sleeps when the first pass succeeds."""

from __future__ import annotations

import app.contrib.gasbuddy_client as gb


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _wire(monkeypatch, passes):
    """Patch the network layer: each element of ``passes`` is the merged
    station list one full pull pass returns. Counts client builds."""
    calls = {"builds": 0, "sleeps": []}
    it = iter(passes)

    monkeypatch.setattr(gb, "_proxy_url", lambda: None)

    def fake_build_client(*, proxy=None, timeout=None):
        calls["builds"] += 1
        return _FakeClient()

    def fake_fetch(client, zips, *, token=None):
        return next(it)

    monkeypatch.setattr(gb, "_build_client", fake_build_client)
    monkeypatch.setattr(gb, "_fetch_lhc_stations_with_client", fake_fetch)
    return calls


def test_success_first_pass_no_retry(monkeypatch):
    calls = _wire(monkeypatch, [[{"id": "1"}]])
    out = gb.fetch_lhc_stations(sleep=lambda s: calls["sleeps"].append(s))
    assert [st["id"] for st in out] == ["1"]
    assert calls["builds"] == 1
    assert calls["sleeps"] == []


def test_empty_pass_retries_on_fresh_client_then_succeeds(monkeypatch):
    calls = _wire(monkeypatch, [[], [{"id": "7"}]])
    out = gb.fetch_lhc_stations(sleep=lambda s: calls["sleeps"].append(s))
    assert [st["id"] for st in out] == ["7"]
    assert calls["builds"] == 2  # a NEW client per pass — fresh session
    assert len(calls["sleeps"]) == 1
    base = gb.EMPTY_RETRY_BASE_SECONDS
    assert base <= calls["sleeps"][0] <= base + gb.EMPTY_RETRY_JITTER_SECONDS


def test_all_empty_gives_up_after_attempts(monkeypatch):
    calls = _wire(monkeypatch, [[], [], []])
    out = gb.fetch_lhc_stations(sleep=lambda s: calls["sleeps"].append(s))
    assert out == []
    assert calls["builds"] == 3
    # sleeps between attempts only (2), with linear backoff
    assert len(calls["sleeps"]) == 2
    assert calls["sleeps"][1] > calls["sleeps"][0]


def test_attempts_floor_of_one(monkeypatch):
    calls = _wire(monkeypatch, [[]])
    out = gb.fetch_lhc_stations(attempts=0, sleep=lambda s: calls["sleeps"].append(s))
    assert out == []
    assert calls["builds"] == 1
    assert calls["sleeps"] == []
