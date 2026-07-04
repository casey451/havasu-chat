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

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static"

# (path, should_be_indexable). The whole Lake Ink & Brass public surface — every
# page that renders on an empty DB — exercised through the full head SEO + asset
# + robots + JSON-LD contract under the lake skin (?theme=lake). Pages that need
# seeded data (/provider/{slug}, /categories/{slug}, /collection/{slug}) are
# covered by their own direct-render tests, not here.
LAKE_PAGES = [
    # indexable public pages
    ("/home?theme=lake", True),
    ("/events-ui?theme=lake", True),
    ("/categories?theme=lake", True),
    ("/map?theme=lake", True),
    ("/gas?theme=lake", True),
    ("/today?theme=lake", True),
    ("/portal?theme=lake", True),
    ("/portal/claim?theme=lake", True),
    ("/about?theme=lake", True),
    ("/help?theme=lake", True),
    ("/contact?theme=lake", True),
    ("/privacy?theme=lake", True),
    ("/terms?theme=lake", True),
    # /sponsor is a real advertiser landing — indexable since v4.4 §7 (noindex dropped).
    ("/sponsor?theme=lake", True),
    # noindex surfaces (auth / discovery / internal)
    ("/login?theme=lake", False),
    ("/calendar?q=live%20music%20this%20weekend", False),
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


@pytest.mark.parametrize("path,_indexable", LAKE_PAGES)
def test_jsonld_blocks_are_valid(client: TestClient, path: str, _indexable: bool) -> None:
    """Every JSON-LD block on every lake page must parse and carry a schema.org
    @context + @type (the spec's "validate JSON-LD in CI"). Catches a malformed
    or unescaped structured-data block sitewide, per page type."""
    body = client.get(path).text
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', body, re.S
    )
    for raw in blocks:
        data = json.loads(raw)  # raises on malformed JSON
        items = data if isinstance(data, list) else [data]
        for item in items:
            assert isinstance(item, dict), f"{path}: JSON-LD item is not an object"
            assert "schema.org" in str(item.get("@context", "")), f"{path}: JSON-LD missing @context"
            assert item.get("@type"), f"{path}: JSON-LD missing @type"


def test_og_image_file_is_a_landscape_card() -> None:
    """The default lake OG card must be the ~1.91:1 social ratio (1200x630)."""
    from PIL import Image

    img = Image.open(_STATIC_ROOT / "img" / "lake" / "og-default.png")
    assert img.size == (1200, 630)


def test_sitemap_lists_public_pages_not_noindex_ones() -> None:
    """The pages sitemap must advertise the indexable public surface (incl. the
    redesign's /today + /portal funnel) and must NOT advertise noindex pages
    (auth/teaser/discovery) — listing a noindex URL is a soft-404 signal."""
    from app.main import _base_url, _build_sitemap_pages_xml

    xml = _build_sitemap_pages_xml()
    base = _base_url()
    for path in ("/home", "/today", "/gas", "/map", "/events-ui", "/categories",
                 "/portal", "/portal/claim", "/about", "/help", "/contact"):
        assert f"{base}{path}</loc>" in xml, f"sitemap missing public page {path}"
    # (/sponsor is indexable since v4.4 §7 but not sitemapped — neither asserted here.)
    for path in ("/login", "/calendar", "/account"):
        assert f"{base}{path}</loc>" not in xml, f"sitemap must not list noindex {path}"


def test_lake_css_self_hosts_fonts_no_google() -> None:
    """lake_redesign.css (the one shell as of v4.6 PR-2) declares @font-face for
    the self-hosted woff2 and never calls Google Fonts at runtime (LCP + privacy)."""
    css = (_STATIC_ROOT / "styles" / "lake_redesign.css").read_text(encoding="utf-8")
    assert "@font-face" in css
    assert "fonts/inter-latin-wght-normal.woff2" in css
    assert "fonts/fraunces-latin-wght-normal.woff2" in css
    assert "fonts.googleapis.com" not in css and "fonts.gstatic.com" not in css
