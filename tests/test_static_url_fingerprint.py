"""1.9b — content-hash fingerprinting for /static URLs (``static_url``).

Pairs with ``CachedStaticFiles``: a ``?v=`` fingerprint earns the immutable
1-year cache, and the hash changes when the bytes change, so a deploy can't
serve stale CSS/JS. Non-static / missing / biz-photos paths pass through bare.
"""

from __future__ import annotations

import hashlib
import re

from app.core.static_assets import _STATIC_ROOT, static_url


def test_appends_content_hash_for_real_asset() -> None:
    css = _STATIC_ROOT / "styles" / "desert.css"
    assert css.is_file(), "fixture asset missing"
    out = static_url("/static/styles/desert.css")
    m = re.fullmatch(r"/static/styles/desert\.css\?v=([0-9a-f]{8})", out)
    assert m, out
    # Fingerprint is the short SHA-1 of the file bytes.
    expected = hashlib.sha1(css.read_bytes()).hexdigest()[:8]
    assert m.group(1) == expected


def test_fingerprint_changes_with_content() -> None:
    """Different bytes → different fingerprint (cache-bust on change)."""
    a = hashlib.sha1(b"a{}").hexdigest()[:8]
    b = hashlib.sha1(b"a {}").hexdigest()[:8]
    assert a != b  # sanity: the hash is content-sensitive


def test_non_static_path_unchanged() -> None:
    assert static_url("/home") == "/home"
    assert static_url("https://cdn.example.com/x.css") == "https://cdn.example.com/x.css"


def test_missing_asset_passes_through() -> None:
    assert static_url("/static/styles/does-not-exist.css") == (
        "/static/styles/does-not-exist.css"
    )


def test_biz_photos_not_fingerprinted() -> None:
    assert static_url("/static/biz-photos/abc.jpg") == "/static/biz-photos/abc.jpg"


def test_existing_query_uses_ampersand() -> None:
    out = static_url("/static/styles/desert.css?foo=1")
    assert "?foo=1&v=" in out


def test_path_traversal_is_refused() -> None:
    # A ``..`` escape resolves outside the static root → no fingerprint, bare path.
    assert static_url("/static/../main.py") == "/static/../main.py"
