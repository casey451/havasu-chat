"""Favicon binary assets + root /favicon.ico route (safe batch 2026-06-11).

These pass only after scripts/gen_favicon_assets.py has generated the binaries
(favicon.ico + the PNG icons) from app/static/img/favicon.svg.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_favicon_ico_served_at_root() -> None:
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/x-icon"


def test_apple_touch_icon_present() -> None:
    r = client.get("/static/img/apple-touch-icon.png")
    assert r.status_code == 200
