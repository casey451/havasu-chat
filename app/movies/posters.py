"""Movie-poster proxy/cache.

Theater posters come from a few external image hosts — the Veezi ticketing CDN
(``ticketing.uswest.veezi.com``) plus the TMDB / AlloCiné art the scraper
enriches with. Veezi enforces **referrer-based hotlink protection** (a browser
loading the image from our pages sends a ``Referer: https://askhava.com/…`` that
Veezi refuses, so the ``<img>`` never completes, ``naturalWidth == 0``), and the
others are external dependencies we don't want a page to silently break on.
Fetching every poster *server-side* — where we control (omit) the referrer — and
re-serving it from our own origin removes the hotlink dependency for all of them.

Two pieces:

* :func:`proxied_poster_url` rewrites a known theater-poster URL into our own
  ``/img/poster?u=…`` route (and leaves any other/empty URL untouched), so the
  templates point ``<img src>`` at our origin.
* :func:`fetch_poster` does the actual server-side fetch behind a strict host
  allowlist (SSRF-safe — it will only ever fetch the known poster hosts) with a
  small in-process bytes cache so repeated loads don't re-hit upstream.
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit

import httpx

# Only these hosts may be proxied. This is the whole point of the allowlist:
# ``/img/poster`` must never become an open proxy that fetches arbitrary (or
# internal) URLs — it can only ever reach the known theater-poster hosts. Veezi
# is the one that actively hotlink-blocks; TMDB + AlloCiné are routed too so no
# ``<img>`` on the movies surface depends on an external host (uniform loading).
_ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "ticketing.uswest.veezi.com",
        "image.tmdb.org",
        "all.web.img.acsta.net",
    }
)

# In-process cache: poster URL -> (bytes, content_type). Posters are small and
# effectively immutable, so a crude size-capped dict (cleared wholesale when
# full) is plenty — no TTL needed, and each worker keeping its own copy is fine.
_CACHE: dict[str, tuple[bytes, str]] = {}
_CACHE_MAX = 256

# Cap a single poster so a hostile/oversized response can't balloon memory.
_MAX_BYTES = 5 * 1024 * 1024


class PosterNotAllowed(ValueError):
    """The requested URL's host is not on the proxy allowlist."""


class PosterFetchError(RuntimeError):
    """The upstream poster could not be fetched (network / non-image / size)."""


def _host_allowed(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _ALLOWED_HOSTS


def proxied_poster_url(url: str | None) -> str | None:
    """Rewrite a known theater-poster URL to our own ``/img/poster`` route.

    URLs on a non-allowlisted host (or empty) are returned unchanged (already
    same-origin, or nothing to proxy), so this is safe to apply to every poster
    field.
    """
    if not url:
        return url
    if _host_allowed(url):
        return "/img/poster?u=" + quote(url, safe="")
    return url


def _http_get(url: str) -> httpx.Response:
    """Server-side GET (no referrer). Seam for tests to patch."""
    return httpx.get(url, timeout=10.0, follow_redirects=True)


def fetch_poster(url: str) -> tuple[bytes, str]:
    """Fetch (and cache) a poster's bytes + content-type.

    Raises :class:`PosterNotAllowed` for a host outside the allowlist and
    :class:`PosterFetchError` for any network / non-image / oversize failure.
    """
    if not _host_allowed(url):
        raise PosterNotAllowed(url)
    cached = _CACHE.get(url)
    if cached is not None:
        return cached
    try:
        resp = _http_get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:  # pragma: no cover - network failure path
        raise PosterFetchError(str(exc)) from exc
    ctype = (resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
    if not ctype.startswith("image/"):
        raise PosterFetchError(f"not an image: {ctype}")
    data = resp.content
    if len(data) > _MAX_BYTES:
        raise PosterFetchError("poster too large")
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[url] = (data, ctype)
    return data, ctype
