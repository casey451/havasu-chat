"""Regression tests for the 2026-07-09 stale-edge-cache class.

Investigation finding (docs/audits/2026-07/STALE_EDGE_CACHE_INVESTIGATION_2026-07-09.md):
there is NO app-level page cache for category / leaf pages — they render fresh
from the DB on every request — so a frozen late-June render is an EDGE (Cloudflare
PoP) artifact, not an origin one. These tests pin the structural defenses shipped
so the class cannot recur by construction:

  * every HTML response binds the CDN with ``Cloudflare-CDN-Cache-Control:
    no-store`` (+ RFC 9213 ``CDN-Cache-Control``), which Cloudflare honors even
    under a "Cache Everything" rule — so a PoP can never STORE an HTML render;
  * every in-process content cache (categories index, sitemap, map) carries the
    running ``build_sha`` in its key, so a deploy invalidates it by construction;
  * the freshness canary samples random bare ``/categories/{dept}/{leaf}`` URLs so
    a frozen-PoP copy of an older build turns the canary red.
"""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

import app.core.build_info as build_info
from app.main import app
from scripts.freshness_canary import (
    Resp,
    bare_subcategory_urls,
    sample_bare_subcategory_urls,
)

client = TestClient(app)


# ── CDN cache-control headers (the edge-freeze kill) ──────────────────────────


@pytest.mark.parametrize("path", ["/home", "/about"])
def test_html_binds_cdn_no_store(path: str) -> None:
    r = client.get(path)
    assert r.headers.get("content-type", "").startswith("text/html")
    # Cloudflare honors this even under a "Cache Everything" Cache Rule — the gap
    # that let a per-PoP HTML copy freeze while the origin said no-store.
    assert r.headers.get("cloudflare-cdn-cache-control") == "no-store"
    assert r.headers.get("cdn-cache-control") == "no-store"
    assert "no-store" in r.headers.get("cache-control", "")


@pytest.mark.parametrize("path", ["/health", "/api/gas"])
def test_health_and_api_skip_cdn_headers(path: str) -> None:
    # /health (Railway probe) + /api/* (JSON) are exempt from the header block.
    r = client.get(path)
    assert r.headers.get("cloudflare-cdn-cache-control") is None
    assert r.headers.get("cdn-cache-control") is None


# ── content caches carry build_sha in the key (deploy = guaranteed miss) ──────


def test_sitemap_cache_invalidates_on_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.seo import site_routes

    site_routes._sitemap_cache.clear()
    calls = {"n": 0}
    real = site_routes._build_sitemap_pages_xml

    def counting() -> str:
        calls["n"] += 1
        return real()

    monkeypatch.setitem(site_routes._SITEMAP_BUILDERS, "pages", counting)
    monkeypatch.setattr(build_info, "build_sha", lambda: "sha-old")
    site_routes._get_cached_sitemap_xml("pages")
    site_routes._get_cached_sitemap_xml("pages")
    assert calls["n"] == 1  # second call hits the cache
    monkeypatch.setattr(build_info, "build_sha", lambda: "sha-new")  # a deploy
    site_routes._get_cached_sitemap_xml("pages")
    assert calls["n"] == 2  # new build_sha → cache miss → rebuild
    site_routes._sitemap_cache.clear()


def test_index_cache_invalidates_on_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.categories import router as cat_router
    from app.db.database import SessionLocal

    cat_router.reset_index_cache()
    calls = {"n": 0}
    real = cat_router._build_index_payload

    def counting(db: object) -> object:
        calls["n"] += 1
        return real(db)

    monkeypatch.setattr(cat_router, "_build_index_payload", counting)
    with SessionLocal() as db:
        monkeypatch.setattr(build_info, "build_sha", lambda: "sha-old")
        cat_router._get_index_payload(db)
        cat_router._get_index_payload(db)
        assert calls["n"] == 1
        monkeypatch.setattr(build_info, "build_sha", lambda: "sha-new")
        cat_router._get_index_payload(db)
        assert calls["n"] == 2
    cat_router.reset_index_cache()


def test_map_cache_invalidates_on_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.routes.map_data as md

    md.reset_map_cache()
    monkeypatch.setattr(build_info, "build_sha", lambda: "sha-old")
    client.get("/api/map_data/pets")
    monkeypatch.setattr(build_info, "build_sha", lambda: "sha-new")
    client.get("/api/map_data/pets")
    keys = set(md._map_cache.keys())
    assert ("sha-old", "pets", False) in keys
    assert ("sha-new", "pets", False) in keys  # a deploy keys a distinct entry
    md.reset_map_cache()


# ── canary samples bare long-tail subcategory URLs ────────────────────────────

_SITEMAP = (
    "<url><loc>https://askhava.com/categories/eat-and-drink</loc></url>"  # dept: 1-seg, skip
    "<url><loc>https://askhava.com/categories/eat-and-drink/quick-bites</loc></url>"
    "<url><loc>https://askhava.com/categories/auto/boat-repair</loc></url>"
    "<url><loc>https://askhava.com/home</loc></url>"  # not a category, skip
    "<url><loc>https://askhava.com/categories/eat-and-drink/quick-bites?open=1</loc></url>"  # param, skip
)


def test_bare_subcategory_urls_two_segment_bare_only() -> None:
    assert bare_subcategory_urls(_SITEMAP) == [
        "/categories/eat-and-drink/quick-bites",
        "/categories/auto/boat-repair",
    ]


def test_sampler_is_bounded_and_never_manufactures_failure() -> None:
    def fetch_ok(path: str, ua: str | None = None) -> Resp:
        assert path == "/sitemap-pages.xml"
        return Resp(200, _SITEMAP)

    picks = sample_bare_subcategory_urls(fetch_ok, rng=random.Random(1), n=1)
    assert len(picks) == 1 and picks[0].startswith("/categories/")

    def fetch_down(path: str, ua: str | None = None) -> Resp:
        return Resp(503, "")

    # A non-200 sitemap yields [] — the sampler must not invent a failure.
    assert sample_bare_subcategory_urls(fetch_down, n=3) == []
