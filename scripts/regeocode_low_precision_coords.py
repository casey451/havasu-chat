"""Re-geocode providers whose lat/lng were truncated to low precision.

~100 providers carry coordinates truncated to 2 decimal places (~1.1 km of
error at this latitude), which lands their /map pin visibly off. This script
finds them (both lat AND lng at <= --max-decimals decimal places — requiring
both axes avoids false positives on genuinely precise coords that happen to
round-trip on one axis), re-geocodes each provider's stored address via the
Google Geocoding API, and writes the full-precision result back to
``Provider.lat/lng`` — plus the entity ``Location`` row via
``sync_provider_entity_from_legacy`` (the /map pin source prefers the entity
Location and falls back to Provider, so both must move together).

DEFAULT IS DRY-RUN: prints per-provider before -> after coordinates and a
summary, writes NOTHING. Pass ``--apply`` to commit.

Idempotent: after a successful ``--apply``, re-geocoded rows carry
full-precision coords and no longer match the low-precision selection, so a
re-run reports 0 candidates / 0 changes.

Safety rails:
* ``GOOGLE_MAPS_API_KEY`` is read from the environment and never printed.
* Polite rate limiting (``--sleep``, default 0.15s between calls).
* Providers with no usable address are skipped (counted, never guessed).
* Geocode results outside a generous Lake Havasu region bounding box are
  rejected (``out_of_bounds``) rather than written — a wild mis-geocode is
  worse than a 2-decimal one.
* No deletes, no schema changes; only lat/lng (+ entity Location sync) move.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\regeocode_low_precision_coords.py            # DRY RUN
    .venv\\Scripts\\python.exe scripts\\regeocode_low_precision_coords.py --apply    # writes
    .venv\\Scripts\\python.exe scripts\\regeocode_low_precision_coords.py --max-decimals 3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Provider  # noqa: E402

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DEFAULT_MAX_DECIMALS = 2
DEFAULT_SLEEP_S = 0.15
_RETRYABLE_STATUSES = ("OVER_QUERY_LIMIT", "UNKNOWN_ERROR")

# Generous sanity box around the Lake Havasu region (Topock to Parker, into
# the Mohave foothills). A geocode result outside this box is almost certainly
# a bad address match, not a real local provider location.
BBOX_LAT_MIN, BBOX_LAT_MAX = 33.9, 35.2
BBOX_LNG_MIN, BBOX_LNG_MAX = -115.0, -113.6

# Appended to bare street addresses ("2851 Saratoga Ave") so the geocoder
# resolves them locally instead of to the highest-ranked US match.
CITY_SUFFIX = "Lake Havasu City, AZ"

_EPS = 1e-9


def has_low_precision(value: float | None, max_decimals: int = DEFAULT_MAX_DECIMALS) -> bool:
    """True when ``value`` has no more than ``max_decimals`` decimal places.

    Float-safe: a coordinate stored as 34.48 may repr as 34.479999...; we
    compare against its rounding within a tiny epsilon rather than parsing
    the string form. ``None`` is never low-precision (it's "no coordinate",
    a different problem than a truncated one).
    """
    if value is None:
        return False
    return abs(value - round(value, max_decimals)) < _EPS


def is_low_precision_pair(
    lat: float | None, lng: float | None, max_decimals: int = DEFAULT_MAX_DECIMALS
) -> bool:
    """True when BOTH axes are low-precision (truncation hits both at once)."""
    return has_low_precision(lat, max_decimals) and has_low_precision(lng, max_decimals)


def usable_address(provider: Provider) -> str | None:
    """The provider address to geocode, with a local city suffix when the
    stored address looks like a bare street address. ``None`` = skip."""
    addr = (provider.address or "").strip()
    if not addr:
        return None
    low = addr.lower()
    if "havasu" in low or "az" in low.replace(",", " ").split():
        return addr
    return f"{addr}, {CITY_SUFFIX}"


def geocode_address(
    client: httpx.Client, address: str, api_key: str, *, retries: int = 3
) -> tuple[float, float] | None:
    """(lat, lng) for ``address`` via Google Geocoding, or ``None`` on no result.

    Retries transient statuses with backoff. Raises ``RuntimeError`` (status
    only — never the URL or key) on a hard failure so a misconfigured key
    stops the run loudly instead of skipping every row.
    """
    last_status = "UNKNOWN"
    for attempt in range(retries):
        resp = client.get(
            GEOCODE_URL, params={"address": address, "key": api_key}, timeout=15.0
        )
        resp.raise_for_status()
        data = resp.json()
        last_status = str(data.get("status"))
        if last_status == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return float(loc["lat"]), float(loc["lng"])
        if last_status == "ZERO_RESULTS":
            return None
        if last_status in _RETRYABLE_STATUSES:
            time.sleep(1.5 * (attempt + 1))
            continue
        break
    raise RuntimeError(f"geocode failed with status {last_status}")


def in_bbox(lat: float, lng: float) -> bool:
    return BBOX_LAT_MIN <= lat <= BBOX_LAT_MAX and BBOX_LNG_MIN <= lng <= BBOX_LNG_MAX


def run(
    *,
    apply: bool = False,
    max_decimals: int = DEFAULT_MAX_DECIMALS,
    limit: int | None = None,
    include_all: bool = False,
    sleep_s: float = DEFAULT_SLEEP_S,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    """Select low-precision providers, re-geocode, report (and write iff apply).

    Returns the summary counts dict (also printed). Idempotent: rows already
    written at full precision no longer select.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GOOGLE_MAPS_API_KEY is not set in the environment.", file=sys.stderr)
        raise SystemExit(2)

    counts = {
        "candidates": 0,
        "changed": 0,
        "unchanged": 0,
        "skipped_no_address": 0,
        "no_result": 0,
        "out_of_bounds": 0,
        "failed": 0,
    }
    own_client = client is None
    http = client or httpx.Client()
    mode = "APPLY" if apply else "DRY-RUN (no writes)"
    try:
        with SessionLocal() as db:
            q = db.query(Provider).filter(Provider.lat.isnot(None), Provider.lng.isnot(None))
            if not include_all:
                q = q.filter(Provider.is_active.is_(True), Provider.draft.is_(False))
            targets = [
                p
                for p in q.order_by(Provider.provider_name).yield_per(500)
                if is_low_precision_pair(p.lat, p.lng, max_decimals)
            ]
            if limit is not None:
                targets = targets[:limit]
            counts["candidates"] = len(targets)
            print(f"[{mode}] {len(targets)} providers with lat/lng at <= "
                  f"{max_decimals} decimal places")

            for i, prov in enumerate(targets):
                addr = usable_address(prov)
                if addr is None:
                    counts["skipped_no_address"] += 1
                    print(f"  SKIP (no address) {prov.id} {prov.provider_name}")
                    continue
                if i and sleep_s > 0:
                    time.sleep(sleep_s)
                try:
                    result = geocode_address(http, addr, api_key)
                except (httpx.HTTPError, RuntimeError) as exc:
                    counts["failed"] += 1
                    print(f"  FAIL {prov.id} {prov.provider_name}: {exc}")
                    continue
                if result is None:
                    counts["no_result"] += 1
                    print(f"  NO RESULT {prov.id} {prov.provider_name}")
                    continue
                new_lat, new_lng = result
                if not in_bbox(new_lat, new_lng):
                    counts["out_of_bounds"] += 1
                    print(f"  OUT OF BOUNDS {prov.id} {prov.provider_name}: "
                          f"({new_lat:.6f}, {new_lng:.6f}) — not written")
                    continue
                if abs(new_lat - prov.lat) < _EPS and abs(new_lng - prov.lng) < _EPS:
                    counts["unchanged"] += 1
                    continue
                counts["changed"] += 1
                print(f"  {prov.id} {prov.provider_name}: "
                      f"({prov.lat}, {prov.lng}) -> ({new_lat:.6f}, {new_lng:.6f})")
                if apply:
                    prov.lat = new_lat
                    prov.lng = new_lng
                    # Keep the entity Location row in step — /map prefers it.
                    sync_provider_entity_from_legacy(db, prov)
            if apply:
                db.commit()
    finally:
        if own_client:
            http.close()

    verb = "changed" if apply else "would change"
    print(f"[{mode}] {verb} {counts['changed']} of {counts['candidates']} candidates; "
          f"skipped_no_address={counts['skipped_no_address']}, "
          f"no_result={counts['no_result']}, out_of_bounds={counts['out_of_bounds']}, "
          f"failed={counts['failed']}, unchanged={counts['unchanged']}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-geocode providers whose lat/lng were truncated to low precision."
    )
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument(
        "--max-decimals",
        type=int,
        default=DEFAULT_MAX_DECIMALS,
        help="treat coords with <= this many decimal places as low-precision (default 2)",
    )
    parser.add_argument("--limit", type=int, default=None, help="process at most N providers")
    parser.add_argument("--all", action="store_true", help="include drafts and inactive rows")
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_S,
        help="seconds to sleep between geocode calls (default 0.15)",
    )
    args = parser.parse_args()
    run(
        apply=args.apply,
        max_decimals=args.max_decimals,
        limit=args.limit,
        include_all=args.all,
        sleep_s=args.sleep,
    )


if __name__ == "__main__":
    main()
