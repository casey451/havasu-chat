"""P1.9 — og:image + complete og tag set on all page types."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _og(html_text: str, prop: str) -> list[str]:
    return re.findall(
        rf'<meta property="og:{prop}" content="([^"]*)"', html_text
    )


@pytest.mark.parametrize("path", ["/home", "/lake-havasu/restaurants", "/events-ui", "/map"])
def test_core_pages_have_full_og_set(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 200
    for prop in ("url", "site_name", "type", "title", "description", "image"):
        values = _og(r.text, prop)
        assert values, f"{path} missing og:{prop}"
        assert len(values) == 1, f"{path} has duplicate og:{prop}"
        assert values[0].strip(), f"{path} has empty og:{prop}"


@pytest.mark.parametrize("path", ["/home", "/lake-havasu/restaurants"])
def test_og_image_is_absolute(client: TestClient, path: str) -> None:
    r = client.get(path)
    (img,) = _og(r.text, "image")
    assert img.startswith("http"), f"og:image must be absolute, got {img!r}"


def test_home_og_title_matches_title_tag(client: TestClient) -> None:
    r = client.get("/home")
    (og_title,) = _og(r.text, "title")
    m = re.search(r"<title>([^<]+)</title>", r.text)
    assert m and og_title.strip() == m.group(1).strip()


def test_og_type_defaults_to_website(client: TestClient) -> None:
    r = client.get("/home")
    assert _og(r.text, "type") == ["website"]
