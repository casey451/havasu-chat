"""HOME_REDESIGN feature-flag tests (PR 1 - editorial lane).

Covers the flag-resolution helper in ``app.home.feature_flags`` directly,
and the end-to-end behaviour through ``GET /home`` (template context
exposes a boolean ``redesign`` flag).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.home import feature_flags
from app.main import app

# ---------------------------------------------------------------------------
# Unit-level: home_redesign_enabled() resolution rules
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure HOME_REDESIGN is unset by default for every test in this module."""
    monkeypatch.delenv("HOME_REDESIGN", raising=False)


def test_flag_off_by_default_no_env_no_override() -> None:
    assert feature_flags.home_redesign_enabled() is False
    assert feature_flags.home_redesign_enabled(None) is False
    assert feature_flags.home_redesign_enabled("") is False


@pytest.mark.parametrize("truthy", ["1", "true", "yes", "on", "TRUE", "Yes", "On"])
def test_flag_on_when_env_truthy(
    monkeypatch: pytest.MonkeyPatch, truthy: str
) -> None:
    monkeypatch.setenv("HOME_REDESIGN", truthy)
    assert feature_flags.home_redesign_enabled() is True


@pytest.mark.parametrize("falsy", ["0", "false", "no", "off", "FALSE"])
def test_flag_off_when_env_falsy(
    monkeypatch: pytest.MonkeyPatch, falsy: str
) -> None:
    monkeypatch.setenv("HOME_REDESIGN", falsy)
    assert feature_flags.home_redesign_enabled() is False


def test_env_unrecognised_reads_as_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anything outside the truthy/falsy vocab is treated as unset (off)."""
    monkeypatch.setenv("HOME_REDESIGN", "maybe")
    assert feature_flags.home_redesign_enabled() is False


def test_query_override_truthy_beats_env_off() -> None:
    """?redesign=1 forces on even when env is unset/false."""
    assert feature_flags.home_redesign_enabled("1") is True
    assert feature_flags.home_redesign_enabled("true") is True


def test_query_override_falsy_beats_env_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """?redesign=0 forces off even when HOME_REDESIGN=1."""
    monkeypatch.setenv("HOME_REDESIGN", "1")
    assert feature_flags.home_redesign_enabled("0") is False
    assert feature_flags.home_redesign_enabled("false") is False


def test_query_override_unparseable_falls_through_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """?redesign=maybe is ignored; the env default applies."""
    monkeypatch.setenv("HOME_REDESIGN", "1")
    assert feature_flags.home_redesign_enabled("maybe") is True
    monkeypatch.delenv("HOME_REDESIGN")
    assert feature_flags.home_redesign_enabled("maybe") is False


# ---------------------------------------------------------------------------
# Integration: GET /home exposes the flag through to the template
# ---------------------------------------------------------------------------


def _has_redesign_marker(html: str) -> bool:
    """The redesign path is now a full template swap to ``home_c.html``.

    Direction C supersedes the Direction A in-template toggle: when the
    flag is on, the router serves ``home_c.html`` which carries a stable
    ``home-c`` body class and a ``c-topbar`` chrome header. We sentinel
    on the body class -- the most stable, unambiguous marker of the new
    template -- so this test survives Direction C template churn (D2+
    will add Discover, Eat row, Services grid, but the chrome stays).
    """
    return 'class="home-c"' in html


def test_get_home_default_no_redesign_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HOME_REDESIGN", raising=False)
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert not _has_redesign_marker(r.text)


def test_get_home_with_env_on_renders_redesign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME_REDESIGN", "1")
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert _has_redesign_marker(r.text)


def test_get_home_with_query_override_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_REDESIGN", raising=False)
    with TestClient(app) as client:
        r = client.get("/home?redesign=1")
    assert r.status_code == 200
    assert _has_redesign_marker(r.text)


def test_get_home_query_override_off_beats_env_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME_REDESIGN", "1")
    with TestClient(app) as client:
        r = client.get("/home?redesign=0")
    assert r.status_code == 200
    assert not _has_redesign_marker(r.text)


def test_get_home_unparseable_override_falls_through_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME_REDESIGN", "1")
    with TestClient(app) as client:
        r = client.get("/home?redesign=maybe")
    assert r.status_code == 200
    assert _has_redesign_marker(r.text)


# Side-effect guarantee: turning the flag on must not change response status
# (rendering must not crash) and must not strip browse affordances entirely.
def test_redesign_on_does_not_break_existing_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HOME_REDESIGN", raising=False)
    with TestClient(app) as client:
        baseline = client.get("/home")
        flagged = client.get("/home?redesign=1")
    assert baseline.status_code == 200
    assert flagged.status_code == 200
    # The legacy template carries the pros & services ``cat-strip`` block;
    # Direction C replaces it with the sticky topbar tab nav. Both paths
    # MUST still expose a way to browse -- we just assert the path-
    # appropriate browse affordance on each side.
    assert "cat-strip" in baseline.text
    assert "c-tabs" in flagged.text
