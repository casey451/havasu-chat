"""zillow_research — Zillow Research housing-market CSVs (market context only).

source-expansion #23. Free ZHVI (home value index) / ZORI (rent index) CSVs by
city and ZIP, published monthly at https://www.zillow.com/research/data/.
Filtered to Lake Havasu City and ZIPs 86403/04/06, stored as a small
market-context cache payload (attribution required).

We do NOT scrape zillow.com listing pages — only the published research CSVs.
Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: the exact CSV file URLs rotate; pass the
current URL via --url or the *_CSV_URL env vars.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "zillow_research"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
TARGET_REGIONS = {"lake havasu city", "86403", "86404", "86406"}
_DATE_COL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LIMITER = SourceLimiter("zillow_research", qps=0.4)

# Best-known city-level CSV endpoints (rotate over time — override via env).
ZHVI_CITY_URL = os.environ.get(
    "ZILLOW_ZHVI_CSV_URL",
    "https://files.zillowstatic.com/research/public_csvs/zhvi/"
    "City_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
)
ZORI_CITY_URL = os.environ.get(
    "ZILLOW_ZORI_CSV_URL",
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "City_zori_uc_sfrcondomfr_sm_month.csv",
)


@dataclass
class MarketStat:
    metric: str
    region_name: str
    region_type: str | None
    latest_date: str | None
    latest_value: float | None
    raw: dict = field(default_factory=dict)


def _latest_value(row: dict[str, str]) -> tuple[str | None, float | None]:
    latest_date: str | None = None
    latest_value: float | None = None
    for key, val in row.items():
        if not key or not _DATE_COL_RE.match(key):
            continue
        if val in (None, ""):
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        if latest_date is None or key > latest_date:
            latest_date, latest_value = key, v
    return latest_date, latest_value


def parse_csv(text: str, *, metric: str) -> list[MarketStat]:
    """Parse a Zillow research CSV, keeping only target Havasu regions."""
    reader = csv.DictReader(io.StringIO(text))
    stats: list[MarketStat] = []
    for row in reader:
        region = (row.get("RegionName") or "").strip()
        if region.lower() not in TARGET_REGIONS:
            continue
        latest_date, latest_value = _latest_value(row)
        stats.append(
            MarketStat(
                metric=metric,
                region_name=region,
                region_type=(row.get("RegionType") or "").strip() or None,
                latest_date=latest_date,
                latest_value=latest_value,
            )
        )
    return stats


def build_cache_payload(stats: list[MarketStat]) -> dict[str, Any]:
    """Assemble a compact market-context cache payload (attribution included)."""
    return {
        "source": SOURCE,
        "attribution": "Zillow Research",
        "stats": [
            {
                "metric": s.metric,
                "region": s.region_name,
                "region_type": s.region_type,
                "as_of": s.latest_date,
                "value": s.latest_value,
            }
            for s in stats
        ],
    }


def fetch_metric(url: str, *, metric: str, client: httpx.Client | None = None) -> list[MarketStat]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/csv"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(url, timeout=60.0))
        if resp is None:
            raise RuntimeError(f"zillow_research fetch failed: {metric}")
        resp.raise_for_status()
        return parse_csv(resp.text, metric=metric)
    finally:
        if owns:
            c.close()


def fetch_all(*, client: httpx.Client | None = None) -> list[MarketStat]:
    return fetch_metric(ZHVI_CITY_URL, metric="ZHVI", client=client) + fetch_metric(
        ZORI_CITY_URL, metric="ZORI", client=client
    )


def stat_sample(s: MarketStat) -> dict:
    return {
        "metric": s.metric,
        "region": s.region_name,
        "as_of": s.latest_date,
        "value": s.latest_value,
    }
