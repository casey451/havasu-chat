"""SEO + asset-integrity contract for the Lake Ink & Brass base (Phase 0).

Node-free, deterministic gates that ride the existing pytest job (so they gate
auto-merge reliably): every lake page must emit a unique title, a bounded meta
description, an absolute-https canonical mirrored to og:url, a full Open
Graph + Twitter card, the web manifest + theme-color, and — crucially — every
``/static`` asset it references must actually exist on disk (a broken
favicon/font/css path is an SEO + perf regression). Internal redesign surfaces
(the styleguide) must be ``noindex``.

As real lake pages land in later phases they get added to ``LAKE_PAGES`` and
inherit this whole contract for free.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static"

# (path, should_be_indexable). Grows as lake pages are migrated.
LAKE_PAGES = [
    ("/lake-styleguide", False),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _meta(body: str, *, prop: str | None = None, name: str | None = None) -> str | None:
    if prop:
        m = re.search(rf'<meta[^>]+property="{re.escape(prop)}"[^>]+content="([^"]*)"', body)
    else:
        m = re.search(rf'<meta[^>]+name="{re.escape(name)}"[^>]+content="([^"]*)"', body)
    return m.group(1) if m else None


@pytest.mark.parametrize("path,_indexable", LAKE_PAGES)
def test_head_seo_contract(client: TestClient, path: str, _indexable: bool) -> None:
    r = client.get(path)
    assert r.status_code == 200
    body = r.text

    title = re.search(r"<title>(.*?)</title>", body, re.S)
    assert title and title.group(1).strip(), f"{path}: missing <title>"

    desc = _meta(body, name="description")
    assert desc, f"{path}: missing meta description"
    assert len(desc) <= 200, f"{path}: meta description too long ({len(desc)})"

    canonical = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', body)
    assert canonical, f"{path}: missing canonical"
    assert canonical.group(1).startswith("https://"), f"{path}: canonical not absolute-https"

    assert _meta(body, prop="og:url") == canonical.group(1), f"{path}: og:url != canonical"
    assert _meta(body, prop="og:title"), f"{path}: missing og:title"
    assert _meta(body, prop="og:description"), f"{path}: missing og:description"
    og_image = _meta(body, prop="og:image")
    assert og_image and og_image.startswith("https://"), f"{path}: og:image not absolute"
    assert _meta(body, name="twitter:card") == "summary_large_image", f"{path}: bad twitter:card"
    assert _meta(body, name="twitter:image"), f"{path}: missing twitter:image"

    assert _meta(body, name="theme-color"), f"{path}: missing theme-color"
    assert 'rel="manifest"' in body, f"{path}: missing manifest link"


@pytest.mark.parametrize("path,indexable", LAKE_PAGES)
def test_robots_directive(client: TestClient, path: str, indexable: bool) -> None:
    r = client.get(path)
    body = r.text
    has_noindex_meta = bool(re.search(r'<meta[^>]+name="robots"[^>]+noindex', body))
    has_noindex_header = "noindex" in (r.headers.get("x-robots-tag") or "")
    if indexable:
        assert not has_noindex_meta and not has_noindex_header, f"{path}: should be indexable"
    else:
        assert has_noindex_meta or has_noindex_header, f"{path}: internal page must be noindex"


@pytest.mark.parametrize("path,_indexable", LAKE_PAGES)
def test_referenced_static_assets_exist(client: TestClient, path: str, _indexable: bool) -> None:
    """Every /static asset the page links must exist on disk (no broken refs)."""
    body = client.get(path).text
    refs = set(re.findall(r'(?:href|src|content)="(/static/[^"]+)"', body))
    assert refs, f"{path}: expected at least one /static asset reference"
    for ref in refs:
        rel = ref[len("/static/"):].split("?", 1)[0].split("#", 1)[0]
        assert (_STATIC_ROOT / rel).is_file(), f"{path}: broken static asset {ref}"


def test_og_image_file_is_a_landscape_card() -> None:
    """The default lake OG card must be the ~1.91:1 social ratio (1200x630)."""
    from PIL import Image

    img = Image.open(_STATIC_ROOT / "img" / "lake" / "og-default.png")
    assert img.size == (1200, 630)


def test_lake_css_self_hosts_fonts_no_google() -> None:
    """lake.css declares @font-face for the self-hosted woff2 and never calls
    Google Fonts at runtime (LCP + privacy)."""
    css = (_STATIC_ROOT / "styles" / "lake.css").read_text(encoding="utf-8")
    assert "@font-face" in css
    assert "fonts/inter-latin-wght-normal.woff2" in css
    assert "fonts/fraunces-latin-wght-normal.woff2" in css
    assert "fonts.googleapis.com" not in css and "fonts.gstatic.com" not in css
