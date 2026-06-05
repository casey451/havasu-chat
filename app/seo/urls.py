"""Canonical absolute-URL helpers (SEO P1.0).

Single source of truth for building absolute, ``https`` canonical / ``og:url``
values. The base origin comes from the ``BASE_URL`` env (set per environment; the
Phase-0 custom-domain swap is then just a ``BASE_URL`` change), falling back to
the production Railway origin.

All URLs are coerced to ``https`` because Railway terminates TLS at the edge and
serves the app over ``http`` internally — a bare ``request.url`` would leak an
``http://`` canonical that search engines treat as a separate, non-secure URL
(the original provider-page bug this module fixes).
"""

from __future__ import annotations

import os
from typing import Any

_DEFAULT_BASE_URL = "https://havasu-chat-production.up.railway.app"


def _coerce_https(url: str) -> str:
    """Force the canonical base URL onto https.

    og:url, canonical, sitemap ``<loc>``, and the robots ``Sitemap`` line must
    all point at the https origin. Coerce ``http`` -> ``https`` and prefix a bare
    host. ``localhost`` / ``127.0.0.1`` are left as-is so local dev keeps working.
    """
    low = url.lower()
    if low.startswith("https://"):
        return url
    if low.startswith("http://"):
        host = url[len("http://") :]
        bare = host.split("/", 1)[0].split(":", 1)[0].lower()
        if bare in ("localhost", "127.0.0.1"):
            return url
        return "https://" + host
    if "://" not in url:
        return "https://" + url
    return url


def base_url() -> str:
    """The canonical site origin (no trailing slash), always https."""
    raw = (os.getenv("BASE_URL") or _DEFAULT_BASE_URL).strip()
    raw = raw.rstrip("/") or _DEFAULT_BASE_URL
    return _coerce_https(raw)


def absolute_url(path: str) -> str:
    """Join ``path`` onto the canonical origin → absolute https URL."""
    p = path or "/"
    if not p.startswith("/"):
        p = "/" + p
    return base_url() + p


def canonical_url(request: Any) -> str:
    """Self-canonical for the current request: absolute https, **path only**.

    The query string is intentionally dropped so faceted variants
    (``?trade=``/``?district=``/``?page=``) canonicalize to the clean category
    path (P1.5 direction). Safe to call from templates with the Starlette
    ``request`` in context.
    """
    try:
        path = request.url.path
    except Exception:
        path = "/"
    return absolute_url(path)
