"""Tests for the VPS watchdog's pure logic (no network, no systemd, no email)."""

from __future__ import annotations

from datetime import datetime, timezone

import scripts.vps_watch as w


def _now() -> datetime:
    return datetime(2026, 6, 25, 14, 0, 0, tzinfo=timezone.utc)


# --- health ---------------------------------------------------------------- #
def test_health_ok() -> None:
    r = w.check_health("http://x/health", getter=lambda u: (200, {"db_connected": True}))
    assert r.ok and r.name == "health"


def test_health_db_down() -> None:
    r = w.check_health("http://x/health", getter=lambda u: (200, {"db_connected": False}))
    assert not r.ok


def test_health_bad_status() -> None:
    assert not w.check_health("http://x/health", getter=lambda u: (503, {})).ok


def test_health_request_explodes() -> None:
    def boom(_):
        raise TimeoutError("nope")

    assert not w.check_health("http://x/health", getter=boom).ok


# --- scraper --------------------------------------------------------------- #
def test_scraper_fresh_success() -> None:
    props = {"Result": "success", "ExecMainStatus": "0", "ExecMainExitTimestamp": "Thu 2026-06-25 13:35:41 UTC"}
    assert w.evaluate_scraper(props, max_age_h=50, now=_now()).ok


def test_scraper_nonzero_exit() -> None:
    props = {"Result": "exit-code", "ExecMainStatus": "1", "ExecMainExitTimestamp": "Thu 2026-06-25 13:35:41 UTC"}
    assert not w.evaluate_scraper(props, max_age_h=50, now=_now()).ok


def test_scraper_stale() -> None:
    props = {"Result": "success", "ExecMainStatus": "0", "ExecMainExitTimestamp": "Sun 2026-06-21 13:35:41 UTC"}
    assert not w.evaluate_scraper(props, max_age_h=50, now=_now()).ok


def test_scraper_never_ran() -> None:
    assert not w.evaluate_scraper({}, max_age_h=50, now=_now()).ok


# --- disk ------------------------------------------------------------------ #
def test_disk(monkeypatch) -> None:
    import collections

    U = collections.namedtuple("U", "total used free")
    monkeypatch.setattr(w.shutil, "disk_usage", lambda p: U(100 * 2**30, 50 * 2**30, 50 * 2**30))
    assert w.check_disk("/", 90).ok
    monkeypatch.setattr(w.shutil, "disk_usage", lambda p: U(100 * 2**30, 95 * 2**30, 5 * 2**30))
    assert not w.check_disk("/", 90).ok


# --- transitions ----------------------------------------------------------- #
def _cr(name, ok):
    return w.CheckResult(name, ok, "")


def test_transition_only_on_change() -> None:
    prev = {"health": True, "scraper": True, "disk": True}
    results = [_cr("health", True), _cr("scraper", False), _cr("disk", True)]
    changed = w.transitions(prev, results)
    assert [c.name for c in changed] == ["scraper"]


def test_transition_recovery() -> None:
    prev = {"scraper": False}
    changed = w.transitions(prev, [_cr("scraper", True)])
    assert changed and changed[0].ok


def test_transition_new_check_counts() -> None:
    assert w.transitions({}, [_cr("health", True)])  # unseen check is a change


def test_bodies_subject_reflects_state() -> None:
    results = [_cr("health", False)]
    subject, html, text = w._bodies("srv1", results, results)
    assert "FAIL" in subject and "health" in text
