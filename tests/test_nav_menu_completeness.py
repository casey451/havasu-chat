"""F10 — the hamburger menu must reach every primary surface, and menu + footer
must use one label per route.

The audit found the mobile menu missing Calendar / Gas / Sign-in and the footer
labeling /categories "The directory" (vs nav "Explore") and /portal "Business
portal" (vs nav "For Business"). These pin the menu completeness and the
single-label rule across the two shells (v4 home = base_redesign; interior pages
= _partials/site_header + site_footer).
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app

# Primary surfaces that must be one tap away from the menu on every page.
_REQUIRED_MENU_LINKS = (
    ">Home<",
    ">Events<",
    ">Calendar<",
    ">News<",
    ">Movies<",
    ">For Kids<",
    ">For Seniors<",
    ">Gas<",
    ">Explore<",
    ">Ask<",
    ">For Business<",
    ">Sign in<",
)


def _v4_home() -> str:
    with TestClient(app) as client:
        prev = os.environ.get("HOME_REDESIGN")
        os.environ["HOME_REDESIGN"] = "1"
        try:
            return client.get("/home").text
        finally:
            if prev is None:
                os.environ.pop("HOME_REDESIGN", None)
            else:
                os.environ["HOME_REDESIGN"] = prev


def _interior() -> str:
    with TestClient(app) as client:
        return client.get("/portal").text


def test_v4_home_menu_reaches_every_primary_surface() -> None:
    body = _v4_home()
    for link in _REQUIRED_MENU_LINKS:
        assert link in body, f"v4 home menu missing {link}"


def test_interior_menu_reaches_every_primary_surface() -> None:
    body = _interior()
    for link in _REQUIRED_MENU_LINKS:
        assert link in body, f"interior menu missing {link}"


def test_menu_and_footer_use_one_label_per_route() -> None:
    body = _interior()
    # /categories is "Explore" everywhere now (not "The directory").
    assert "The directory" not in body
    assert ">Explore<" in body
    # /portal is "For Business" everywhere now (not "Business portal").
    assert "Business portal" not in body
    assert ">For Business<" in body
