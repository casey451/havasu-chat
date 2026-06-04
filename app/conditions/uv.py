"""UV-index orchestrator — Open-UV (key-gated) with a keyless EPA fallback.

Task 0 of the source-expansion work surfaces a UV tile in place of the
low-value "Sunny" sky chip. UV must be *robust*: it should render even when no
``OPENUV_API_KEY`` is configured. This module is the single fetcher the
conditions pipeline wires for ``SOURCE_OPENUV``:

1. **Primary — Open-UV** (``app/conditions/openuv.py``): live measured UV, used
   when ``OPENUV_API_KEY`` is set. Free tier 50 req/day; the hourly source TTL
   keeps usage to ~24 calls/day.
2. **Fallback — EPA Envirofacts** (``app/conditions/epa_uv.py``): keyless
   hourly UV *forecast* by ZIP. Used when Open-UV is unconfigured or returns
   nothing usable.

Both branches normalise to ``{"uv_index", "uv_max", "uv_severity", "uv_source"}``
so the api_payload / view_model layers don't care which one supplied the number.
Returns ``{}`` when neither source yields a value, so the strip degrades
gracefully (no UV tile rather than a fabricated one).
"""

from __future__ import annotations

from typing import Any

from app.conditions import epa_uv, openuv

UV_SOURCE_OPENUV = "Open-UV"
UV_SOURCE_EPA = "EPA UV index"


def uv_severity(uv: float) -> str:
    """WHO UV-index exposure bands → conditions-strip severity."""
    if uv < 3:
        return "good"
    if uv < 6:
        return "moderate"
    if uv < 8:
        return "warning"
    return "severe"


def fetch_uv_index() -> dict[str, Any]:
    """Return ``{"uv_index", "uv_max", "uv_severity", "uv_source"}`` or ``{}``.

    Prefers Open-UV (when keyed); falls back to the keyless EPA forecast. Safe
    to call on every conditions-cron tick regardless of configuration — neither
    branch makes an HTTP call it can't service (Open-UV no-ops without a key).
    """
    primary = openuv.fetch_openuv_index()
    uv = primary.get("uv_index") if isinstance(primary, dict) else None
    if isinstance(uv, (int, float)):
        out = dict(primary)
        out.setdefault("uv_severity", uv_severity(float(uv)))
        out["uv_source"] = UV_SOURCE_OPENUV
        return out

    fallback = epa_uv.fetch_epa_uv_index()
    uv = fallback.get("uv_index") if isinstance(fallback, dict) else None
    if isinstance(uv, (int, float)):
        out = dict(fallback)
        out["uv_severity"] = uv_severity(float(uv))
        out["uv_source"] = UV_SOURCE_EPA
        return out

    return {}
