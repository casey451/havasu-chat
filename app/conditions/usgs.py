"""USGS OGC API — Lake Havasu gauge 09427500 (Phase 8a; Phase 8a.2 collection rename)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.contrib.rate_limiter import SourceLimiter

_USGS_LIMITER = SourceLimiter("usgs", qps=0.5)
_OGC_BASE = "https://api.waterdata.usgs.gov/ogcapi/v0"

# Phase 8a.2 (2026-05-21): USGS Water Data OGC API renamed the `observations`
# collection to `latest-continuous` (other companion collections now exist —
# `continuous`, `daily`, `latest-daily`, `field-measurements`). The legacy
# `observations` path returns HTTP 404 `{"code":"NotFound","description":
# "Collection not found"}`. The new collection returns the same FeatureCollection
# shape; per-feature `properties` may use either `datetime` or `time` as the
# timestamp key (the parser below handles both), and `value` is a string in the
# new payload (the parser already coerces via `float(value)`).
_OGC_COLLECTION = "latest-continuous"


def fetch_usgs_lake_havasu() -> dict[str, Any]:
    site = os.environ.get("USGS_LAKE_HAVASU_SITE", "09427500")
    codes = os.environ.get("USGS_PARAMETER_CODES", "00065,00054")
    param_list = [c.strip() for c in codes.split(",") if c.strip()]

    gauge_ft: float | None = None
    storage_acft: float | None = None
    history: list[dict[str, Any]] = []

    with httpx.Client(timeout=15.0) as client:
        for code in param_list:

            def _inner(c: httpx.Client = client, pcode: str = code) -> httpx.Response:
                return c.get(
                    f"{_OGC_BASE}/collections/{_OGC_COLLECTION}/items",
                    params={
                        "monitoring_location_id": f"USGS-{site}",
                        "parameter_code": pcode,
                        "limit": 2,
                    },
                )

            # Phase 8a.0 hotfix 2026-05-21: SourceLimiter.call_with_retry takes
            # a no-arg callable. USGS's `_inner` already defaults-closes over
            # `client` + `pcode`, so just drop the extra positional arg.
            response = _USGS_LIMITER.call_with_retry(_inner)
            if response is None:
                continue
            response.raise_for_status()
            payload = response.json()
            features = payload.get("features") or []
            for feat in features:
                if not isinstance(feat, dict):
                    continue
                props = feat.get("properties") or {}
                value = props.get("value")
                ts = props.get("datetime") or props.get("time")
                if value is None:
                    continue
                try:
                    val_f = float(value)
                except (TypeError, ValueError):
                    continue
                history.append({"parameter_code": code, "value": val_f, "observed_at": ts})
                if code == "00065" and gauge_ft is None:
                    gauge_ft = val_f
                elif code == "00054" and storage_acft is None:
                    storage_acft = val_f

    prior_gauge = None
    if len(history) >= 2:
        for item in history:
            if item.get("parameter_code") == "00065":
                prior_gauge = item.get("value")
                break

    return {
        "site": site,
        "lake_gauge_ft": gauge_ft,
        "lake_storage_acft": storage_acft,
        "prior_gauge_ft": prior_gauge,
        "history": history,
    }
