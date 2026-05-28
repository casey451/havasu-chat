"""Direction C /home redesign tests (post legacy home retirement)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_home_serves_home_c_by_default() -> None:
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert "home_c.css" in r.text
    assert 'class="home-c"' in r.text
    assert "Ask Hava" in r.text
    assert "c-hava-read" in r.text


def test_home_redesign_query_param_still_serves_home_c() -> None:
    with TestClient(app) as client:
        for path in ("/home?redesign=0", "/home?redesign=1"):
            r = client.get(path)
            assert r.status_code == 200
            assert "home_c.css" in r.text


def test_direction_c_no_mock_content() -> None:
    with TestClient(app) as client:
        r = client.get("/home")
    for leaked in ("Channel Brewing Co.", "Aquatic Center", "Havasu Outdoor Co."):
        assert leaked not in r.text, f"home_c.html leaked mock content: {leaked}"


def test_direction_c_has_tab_anchors() -> None:
    with TestClient(app) as client:
        r = client.get("/home")
    assert "Eat &amp; drink" in r.text or "Eat & drink" in r.text
    assert 'href="/categories/eat-drink"' in r.text
    assert 'href="/categories/on-the-water"' in r.text
    assert 'href="/categories/things-to-do"' in r.text
    assert 'href="/categories/services"' in r.text
    assert "is-active" in r.text
    assert 'aria-current="page"' in r.text
