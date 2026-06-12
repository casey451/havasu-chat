"""Content-hash fingerprinting for ``/static`` asset URLs (UI plan 1.9b).

Pairs with ``CachedStaticFiles`` in ``app.main``: a request whose query string
carries a ``v=`` fingerprint is served ``Cache-Control: public,
max-age=31536000, immutable``; a bare request gets a short, self-healing
``max-age``. ``static_url`` produces the fingerprinted form so a template can
opt an asset into the immutable cache:

    <link rel="stylesheet" href="{{ static_url('/static/styles/desert.css') }}">
    → /static/styles/desert.css?v=1a2b3c4d

The fingerprint is a short SHA-1 of the file's **bytes**, so it changes exactly
when the file changes — a deploy can never serve a stale pinned copy. The value
is memoized per process; Railway restarts the process on deploy, so the hash is
recomputed from the new bytes automatically. When the file is missing, the path
isn't under ``/static``, or it's the dynamic ``biz-photos`` mount, the bare path
is returned unchanged (it still gets the short default cache).
"""

from __future__ import annotations

import functools
import hashlib
from pathlib import Path

_STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"
_STATIC_PREFIX = "/static/"


@functools.lru_cache(maxsize=512)
def _fingerprint(rel_path: str) -> str | None:
    """Short content hash for ``app/static/<rel_path>``; ``None`` if unreadable.

    Resolves and confines the path under the static root so a crafted
    ``..`` segment can't read outside it.
    """
    try:
        target = (_STATIC_ROOT / rel_path).resolve()
        target.relative_to(_STATIC_ROOT.resolve())
        data = target.read_bytes()
    except (OSError, ValueError):
        return None
    return hashlib.sha1(data).hexdigest()[:8]


def static_url(path: str) -> str:
    """Append a content-hash ``?v=`` to a ``/static`` URL for immutable caching.

    Returns ``path`` unchanged when it isn't a fingerprintable static asset
    (non-``/static`` path, the dynamic ``biz-photos`` mount, or a missing file)
    — those still receive the short default ``Cache-Control`` from
    ``CachedStaticFiles``.
    """
    if not path or not path.startswith(_STATIC_PREFIX):
        return path
    rel = path[len(_STATIC_PREFIX) :].split("?", 1)[0].split("#", 1)[0]
    # biz-photos is a separate, runtime-populated mount, not part of app/static.
    if rel.startswith("biz-photos/"):
        return path
    version = _fingerprint(rel)
    if version is None:
        return path
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}v={version}"
