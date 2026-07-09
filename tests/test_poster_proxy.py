"""Movie-poster proxy: URL rewriting + the host-allowlisted /img/poster route.

The theater feed (Veezi) hotlink-protects its poster host by referrer, so the
live ``<img>`` never loads. We re-serve posters from our own origin: the poster
URL is rewritten to ``/img/poster?u=…`` and the route fetches the bytes
server-side (only for the allowlisted Veezi host — never an open proxy).
"""

from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.movies import posters
from app.movies.queries import group_showtimes
from tests.test_movies_queries import DAY, ms

_VEEZI = (
    "https://ticketing.uswest.veezi.com/Media/Poster"
    "?siteToken=abc&code=0000001431&isHighRes=true"
)


def test_proxied_poster_url_rewrites_known_theater_hosts():
    out = posters.proxied_poster_url(_VEEZI)
    assert out == "/img/poster?u=" + quote(_VEEZI, safe="")
    # All theater poster hosts route through the proxy so no <img> hotlinks an
    # external host (the acsta posters were the un-proxied 8/18 in live QA).
    for url in (
        "https://image.tmdb.org/t/p/w500/abc.jpg",
        "https://all.web.img.acsta.net/img/58/fa/abc.jpg",
    ):
        assert posters.proxied_poster_url(url) == "/img/poster?u=" + quote(url, safe="")
    # Unknown / empty hosts are left untouched (already same-origin or nothing).
    assert posters.proxied_poster_url("https://example.com/p.jpg") == "https://example.com/p.jpg"
    assert posters.proxied_poster_url(None) is None
    assert posters.proxied_poster_url("") == ""


def test_group_showtimes_proxies_veezi_poster():
    rows = [ms("Veezi Film", "star-cinemas", 12, name="Star Cinemas", poster=_VEEZI)]
    film = group_showtimes(rows, day=DAY)[0].films[0]
    assert film.poster == "/img/poster?u=" + quote(_VEEZI, safe="")


def test_poster_route_rejects_non_allowlisted_host():
    r = TestClient(app).get("/img/poster", params={"u": "https://evil.example.com/x.png"})
    assert r.status_code == 400


def test_poster_route_serves_allowlisted_bytes(monkeypatch):
    posters._CACHE.clear()
    png = b"\x89PNG\r\n\x1a\n" + b"fake-bytes"

    class _Resp:
        headers = {"content-type": "image/png"}
        content = png

        def raise_for_status(self):
            return None

    monkeypatch.setattr(posters, "_http_get", lambda url: _Resp())
    r = TestClient(app).get("/img/poster", params={"u": _VEEZI})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == png
    assert "max-age" in r.headers.get("cache-control", "")


def test_poster_route_502_on_upstream_failure(monkeypatch):
    posters._CACHE.clear()

    def _boom(url):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(posters, "_http_get", _boom)
    r = TestClient(app).get("/img/poster", params={"u": _VEEZI})
    assert r.status_code == 502
