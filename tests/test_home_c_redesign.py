"""Direction C /home redesign tests (PR D1 -- dark chrome + tabs scaffold).

Two surfaces under test:

1. ``HAVA_DEMO_MODE`` env-var gate in ``app.home.demo_mode`` (unit-level).
2. ``GET /home`` template switching: legacy ``home.html`` when the
   ``HOME_REDESIGN`` flag is off; the new dark-chrome ``home_c.html``
   when on. Mirrors the convention used by
   ``tests/test_home_feature_flag.py`` -- monkeypatch for env vars,
   inline ``with TestClient(app) as client:`` per test, no shared
   fixture.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.home import demo_mode
from app.main import app

# ---------------------------------------------------------------------------
# HAVA_DEMO_MODE gate
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure HOME_REDESIGN and HAVA_DEMO_MODE start unset for every test."""
    monkeypatch.delenv("HOME_REDESIGN", raising=False)
    monkeypatch.delenv("HAVA_DEMO_MODE", raising=False)


def test_demo_mode_default_off() -> None:
    """Unset env reads as off (production-safe default)."""
    assert demo_mode.demo_mode_enabled() is False


@pytest.mark.parametrize(
    "val", ["1", "true", "True", "yes", "YES", "on", "On"]
)
def test_demo_mode_truthy(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv("HAVA_DEMO_MODE", val)
    assert demo_mode.demo_mode_enabled() is True


@pytest.mark.parametrize(
    "val", ["0", "false", "no", "off", "", "maybe", "?"]
)
def test_demo_mode_falsy_or_unparseable(
    monkeypatch: pytest.MonkeyPatch, val: str
) -> None:
    monkeypatch.setenv("HAVA_DEMO_MODE", val)
    assert demo_mode.demo_mode_enabled() is False


# ---------------------------------------------------------------------------
# Template switching by HOME_REDESIGN flag
# ---------------------------------------------------------------------------


def test_home_redesign_off_serves_legacy_template() -> None:
    """HOME_REDESIGN unset: GET /home serves legacy home.html (no Direction C markers)."""
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    # Direction C sentinel ABSENT
    assert "home_c.css" not in r.text
    assert 'class="home-c"' not in r.text


def test_home_redesign_query_override_serves_direction_c() -> None:
    """?redesign=1 override flips to home_c.html regardless of env."""
    with TestClient(app) as client:
        r = client.get("/home?redesign=1")
    assert r.status_code == 200
    assert "home_c.css" in r.text
    assert "c-tab" in r.text


def test_home_redesign_env_on_serves_direction_c(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HOME_REDESIGN=1 in env serves home_c.html."""
    monkeypatch.setenv("HOME_REDESIGN", "1")
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert "home_c.css" in r.text
    assert "Ask Hava" in r.text  # composer label / hero h1


def test_home_redesign_query_off_overrides_env_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """?redesign=0 wins over HOME_REDESIGN=1 env (staff preview off)."""
    monkeypatch.setenv("HOME_REDESIGN", "1")
    with TestClient(app) as client:
        r = client.get("/home?redesign=0")
    assert r.status_code == 200
    assert "home_c.css" not in r.text


# ---------------------------------------------------------------------------
# Direction C content sanity
# ---------------------------------------------------------------------------


def test_direction_c_no_mock_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """home_c.html should not leak any mock_data names. D1 has no grids."""
    monkeypatch.setenv("HOME_REDESIGN", "1")
    # HAVA_DEMO_MODE is unset by the autouse fixture above.
    with TestClient(app) as client:
        r = client.get("/home")
    for leaked in ("Channel Brewing Co.", "Aquatic Center", "Havasu Outdoor Co."):
        assert leaked not in r.text, f"D1 home_c.html leaked mock content: {leaked}"


def test_direction_c_has_tab_anchors(monkeypatch: pytest.MonkeyPatch) -> None:
    """PR D5 promoted the four right-side tabs from <button disabled>
    to <a href="/categories/{slug}">. The Today pill is also an anchor
    (back to /home itself) -- it's marked active when on /home."""
    monkeypatch.setenv("HOME_REDESIGN", "1")
    with TestClient(app) as client:
        r = client.get("/home")
    # Match both encoded and unencoded for resilience
    assert "Eat &amp; drink" in r.text or "Eat & drink" in r.text
    # All four mega-tab routes are linked from /home.
    assert 'href="/categories/eat-drink"' in r.text
    assert 'href="/categories/on-the-water"' in r.text
    assert 'href="/categories/things-to-do"' in r.text
    assert 'href="/categories/services"' in r.text
    # Today tab is marked active (PR D5 leaves Today inert as an anchor
    # back to /home, but with is-active + aria-current="page").
    assert "is-active" in r.text
    assert 'aria-current="page"' in r.text
