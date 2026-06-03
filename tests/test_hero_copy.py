"""Configurable /home hero copy (eyebrow + headline) tests.

The Sandstone home defaults to the locked prototype hero wording, but keeps the
env-override capability so owners can retune the copy per season/campaign without
a redeploy.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_home_renders_default_hero_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_HERO_EYEBROW", raising=False)
    monkeypatch.delenv("HOME_HERO_HEADLINE", raising=False)
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    # Locked prototype hero: dated eyebrow + the concierge question headline.
    assert "Your lake ·" in r.text
    assert "What's the plan on" in r.text
    # Legacy hardcoded copy is gone.
    assert "WELCOME BACK" not in r.text
    assert "What are you in the mood for?" not in r.text


def test_home_hero_headline_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_HERO_HEADLINE", "Beat the heat at the channel")
    monkeypatch.setenv("HOME_HERO_EYEBROW", "HELLO HAVASU")
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert "Beat the heat at the channel" in r.text
    assert "HELLO HAVASU" in r.text
    # The prototype default must not leak when overridden.
    assert "What's the plan on" not in r.text
