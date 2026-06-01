"""Orchestration: per-station Lake Havasu City gas prices -> cache payload.

GasBuddy is the primary source (full station coverage, crowd-updated).
Google Places ``fuelOptions`` is the fallback: it fills stations GasBuddy
missed (matched to existing gas-station Providers by ``google_place_id``)
and supplements grades GasBuddy did not return.

The merged result is stored as ONE JSON payload in
``external_conditions_cache`` under ``SOURCE_GAS`` -- no migration, reuses the
conditions cache + circuit-breaker. ``/api/conditions`` and the ``/gas`` page
read it back.

CLI: ``scripts/gas_prices_pull.py`` (supports ``--dry-run``).
ASCII-only by project convention.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conditions.cache import record_fetch_failure, upsert_source
from app.conditions.constants import SOURCE_GAS, TTL_BY_SOURCE
from app.contrib import gasbuddy_client, places_fuel
from app.db.models import Provider

logger = logging.getLogger(__name__)

GRADES: tuple[str, ...] = ("regular", "midgrade", "premium", "diesel")

# GasBuddy fuelProduct keys -> our canonical grade keys.
_GB_PRODUCT_TO_GRADE: dict[str, str] = {
    "regular_gas": "regular",
    "midgrade_gas": "midgrade",
    "premium_gas": "premium",
    "diesel": "diesel",
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _norm_name(s: str | None) -> str:
    """Normalize a station/brand name for fuzzy matching."""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # Drop common station-name noise words.
    s = re.sub(r"\b(gas|station|fuel|fuels|the|inc|llc|co)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _street_number(addr: str | None) -> str | None:
    if not addr:
        return None
    m = re.match(r"\s*(\d+)", addr)
    return m.group(1) if m else None


def _price_from_node(node: dict[str, Any] | None) -> float | None:
    """Pull a numeric price from a GasBuddy price node (credit/cash)."""
    if not isinstance(node, dict):
        return None
    raw = node.get("price")
    try:
        val = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        val = None
    if val is None or val <= 0:
        return None
    return round(val, 3)


def normalize_gasbuddy_station(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert one raw GasBuddy station node into our canonical station dict."""
    addr = raw.get("address") if isinstance(raw.get("address"), dict) else {}
    line1 = (addr.get("line1") or "").strip()
    brands = raw.get("brands") if isinstance(raw.get("brands"), list) else []
    brand = ""
    if brands and isinstance(brands[0], dict):
        # LOCATION_QUERY_PRICES returns brands {brandId name}; older shapes
        # used brandName -- accept either.
        brand = (brands[0].get("name") or brands[0].get("brandName") or "").strip()

    prices: dict[str, float] = {}
    posted_time: str | None = None
    for pr in raw.get("prices") or []:
        if not isinstance(pr, dict):
            continue
        grade = _GB_PRODUCT_TO_GRADE.get(str(pr.get("fuelProduct") or ""))
        if not grade:
            continue
        amount = _price_from_node(pr.get("credit")) or _price_from_node(pr.get("cash"))
        if amount is None:
            continue
        prices[grade] = amount
        node = pr.get("credit") if isinstance(pr.get("credit"), dict) else pr.get("cash")
        pt = node.get("postedTime") if isinstance(node, dict) else None
        if isinstance(pt, str) and (posted_time is None or pt > posted_time):
            posted_time = pt

    return {
        "source": "gasbuddy",
        "gasbuddy_id": str(raw.get("id") or "") or None,
        "name": (raw.get("name") or brand or "Gas station").strip(),
        "brand": brand or None,
        "address": line1 or None,
        "lat": raw.get("latitude"),
        "lng": raw.get("longitude"),
        "prices": prices,
        "posted_time": posted_time,
        "provider_slug": None,
    }


def _load_gas_station_providers(db: Session) -> list[Provider]:
    stmt = (
        select(Provider)
        .where(Provider.google_primary_category == "gas_station")
        .where(Provider.is_active.is_(True))
        .where(Provider.draft.is_(False))
    )
    return list(db.execute(stmt).scalars().all())


def _match_provider(station: dict[str, Any], providers: list[Provider]) -> Provider | None:
    """Best-effort match a GasBuddy station to a Provider (name + street #)."""
    st_name = _norm_name(station.get("name")) or _norm_name(station.get("brand"))
    st_num = _street_number(station.get("address"))
    if not st_name:
        return None
    best: Provider | None = None
    for p in providers:
        p_name = _norm_name(p.provider_name)
        if not p_name:
            continue
        name_hit = st_name in p_name or p_name in st_name or st_name.split(" ")[0] == p_name.split(" ")[0]
        if not name_hit:
            continue
        p_num = _street_number(p.address)
        if st_num and p_num and st_num == p_num:
            return p  # strong match
        if best is None:
            best = p
    return best


def build_gas_payload(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Fetch + merge gas prices and return the cache payload (no DB write)."""
    now = now or _utc_now()
    providers = _load_gas_station_providers(db)
    logger.info("Loaded %d gas_station providers for matching/fallback", len(providers))

    # 1) GasBuddy primary.
    gb_raw = gasbuddy_client.fetch_lhc_stations()
    stations: list[dict[str, Any]] = [normalize_gasbuddy_station(r) for r in gb_raw]
    stations = [s for s in stations if s.get("prices")]
    matched_provider_ids: set[str] = set()
    for s in stations:
        prov = _match_provider(s, providers)
        if prov is not None:
            s["provider_slug"] = prov.slug
            matched_provider_ids.add(prov.id)

    gasbuddy_count = len(stations)

    # Dedupe key (normalized name + street number) for stations we already have.
    def _dedupe_key(name: str | None, address: str | None) -> str:
        return f"{_norm_name(name)}|{_street_number(address) or ''}"

    have_keys: set[str] = {_dedupe_key(s.get("name"), s.get("address")) for s in stations}

    # 2) Google Places fuelOptions fallback. Discovers gas stations directly
    #    via Places text search (independent of the catalog, which may have no
    #    gas_station providers) and adds any with prices that GasBuddy missed.
    #    Only runs when GOOGLE_PLACES_API_KEY is configured.
    google_count = 0
    try:
        with httpx.Client(timeout=places_fuel.REQUEST_TIMEOUT) as gclient:
            discovered = places_fuel.discover_gas_stations(client=gclient)
            for ds in discovered:
                if _dedupe_key(ds.get("name"), ds.get("address")) in have_keys:
                    continue
                fo = places_fuel.fetch_fuel_options(ds["place_id"], client=gclient)
                if not fo:
                    continue
                # Attach a provider slug if one matches (deep-link), else None.
                pseudo = {"name": ds.get("name"), "brand": None, "address": ds.get("address")}
                prov = _match_provider(pseudo, providers)
                stations.append(
                    {
                        "source": "google",
                        "gasbuddy_id": None,
                        "google_place_id": ds["place_id"],
                        "name": ds.get("name"),
                        "brand": None,
                        "address": ds.get("address"),
                        "lat": ds.get("lat"),
                        "lng": ds.get("lng"),
                        "prices": fo["prices"],
                        "posted_time": fo.get("update_time"),
                        "provider_slug": prov.slug if prov is not None else None,
                    }
                )
                have_keys.add(_dedupe_key(ds.get("name"), ds.get("address")))
                google_count += 1
    except RuntimeError as exc:
        # No GOOGLE_PLACES_API_KEY -- fallback simply unavailable; not fatal.
        logger.warning("Google fuelOptions fallback skipped: %s", exc)

    # 3) Rank. Cheapest by regular, then any available grade. Name is the
    #    final tie-break so equal-priced stations keep a stable, deterministic
    #    order run-to-run (Google discovery order is not stable).
    def _sort_key(s: dict[str, Any]) -> tuple[int, float, str]:
        pr = s.get("prices") or {}
        name = (s.get("name") or "").lower()
        if "regular" in pr:
            return (0, pr["regular"], name)
        cheapest_any = min(pr.values()) if pr else 9999.0
        return (1, cheapest_any, name)

    stations.sort(key=_sort_key)
    cheapest = [s for s in stations if "regular" in (s.get("prices") or {})][:5]
    if not cheapest:
        cheapest = stations[:5]

    # City average per grade (mean of available station prices).
    city_avg: dict[str, float] = {}
    for g in GRADES:
        vals = [s["prices"][g] for s in stations if g in (s.get("prices") or {})]
        if vals:
            city_avg[g] = round(sum(vals) / len(vals), 3)

    return {
        "updated_at_iso": _iso(now),
        "station_count": len(stations),
        "source_counts": {"gasbuddy": gasbuddy_count, "google": google_count},
        "city_avg": city_avg,
        "cheapest": cheapest,
        "stations": stations,
    }


def store_gas_payload(db: Session, payload: dict[str, Any], *, now: datetime | None = None) -> None:
    """Upsert the gas payload into external_conditions_cache."""
    upsert_source(
        db,
        SOURCE_GAS,
        payload,
        ttl_seconds=TTL_BY_SOURCE.get(SOURCE_GAS),
        success=True,
        now=now,
    )
    db.commit()


def run_pull(*, dry_run: bool = False) -> int:
    """CLI entry point. Returns a process exit code (0 ok, 1 no data/error)."""
    from app.db.database import SessionLocal

    now = _utc_now()
    db = SessionLocal()
    try:
        try:
            payload = build_gas_payload(db, now=now)
        except Exception as exc:  # noqa: BLE001 - record + surface for the cron
            logger.exception("gas price pull failed")
            if not dry_run:
                record_fetch_failure(db, SOURCE_GAS, str(exc), now=now)
                db.commit()
            print(f"ERROR: gas price pull failed: {exc}")
            return 1

        sc = payload["source_counts"]
        print(
            f"stations={payload['station_count']} "
            f"(gasbuddy={sc['gasbuddy']}, google={sc['google']})"
        )
        print(f"city_avg={payload['city_avg']}")
        print("cheapest (top 5 by regular):")
        for s in payload["cheapest"]:
            reg = (s.get("prices") or {}).get("regular")
            print(
                f"  ${reg if reg is not None else '?':<6} "
                f"{s.get('name'):<32} {s.get('address') or ''} [{s.get('source')}]"
            )

        if payload["station_count"] == 0:
            print("WARNING: no stations with prices found -- not writing cache.")
            return 1

        if dry_run:
            print("\n[dry-run] not writing to external_conditions_cache.")
            return 0

        store_gas_payload(db, payload, now=now)
        print(f"\nWrote payload to external_conditions_cache source={SOURCE_GAS!r}.")
        return 0
    finally:
        db.close()
