"""Scheme-safe href helper for hand-built admin HTML (audit M2).

`html.escape(quote=True)` (the existing `_esc`/`_escape` in the admin modules)
prevents HTML-attribute breakout but does NOT neutralize dangerous URL schemes
(`javascript:`, `data:`, `vbscript:`). Admin pages render URLs that originate
from external scrapers — `Event.event_url`, `Contribution.source_url`, neither
of which is `HttpUrl`-validated — into `<a href="...">`. A malicious or
compromised source could set `event_url = "javascript:..."` that runs in the
authenticated admin session when an admin clicks it.

`safe_href` returns the URL only if it is http(s) or a root-relative path;
anything else collapses to "#". Compose with the existing escaper for attribute
safety:

    f'<a href="{_escape(safe_href(url))}" ...>'
"""

from __future__ import annotations

from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def safe_href(url: str | None) -> str:
    """Return `url` only if it's an http(s) or root-relative link, else "#"."""
    if not url:
        return "#"
    candidate = url.strip()
    if not candidate:
        return "#"
    # Root-relative links are safe; protocol-relative ("//evil.com") is not.
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    try:
        scheme = urlparse(candidate).scheme.lower()
    except ValueError:
        return "#"
    return candidate if scheme in _ALLOWED_SCHEMES else "#"
