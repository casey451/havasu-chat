"""G-3: fuel stations carry a deep-link to their Provider even when the catalog
files them under a fuel-adjacent primary (truck_stop / convenience_store)
rather than ``gas_station``.

Before the fix, ``_load_gas_station_providers`` filtered to
``google_primary_category == "gas_station"`` only, so Pilot (truck_stop) and
Terrible Herbst / Hacienda (convenience_store) had no candidate row and rendered
unlinked. The pool now spans ``_FUEL_PRIMARY_CATEGORIES``; matching stays
name+street gated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.contrib import gas_prices
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Entity, Provider
from app.db.seed_helpers import derive_provider_slug


def _seed(name: str, primary: str, address: str) -> str:
    with SessionLocal() as s:
        p = Provider(
            provider_name=name,
            category="auto",
            slug=derive_provider_slug(s, name),
            source="google_places",
            google_primary_category=primary,
            address=address,
            draft=False,
            is_active=True,
        )
        s.add(p)
        create_provider_and_entity(s, p)
        s.flush()
        pid = p.id
        s.commit()
        return pid


def _cleanup(ids: list[str]) -> None:
    with SessionLocal() as s:
        provs = s.scalars(select(Provider).where(Provider.id.in_(ids))).all()
        ent_ids = [p.entity_id for p in provs if p.entity_id]
        for p in provs:
            s.delete(p)
        s.flush()
        for ent in s.scalars(select(Entity).where(Entity.id.in_(ent_ids))).all():
            s.delete(ent)
        s.commit()


def test_pool_includes_fuel_adjacent_primaries() -> None:
    """truck_stop + convenience_store providers join the candidate pool."""
    tag = uuid.uuid4().hex[:8]
    ids = [
        _seed(f"Pilot Travel Center {tag}", "truck_stop", "100 Hwy 95, Lake Havasu City"),
        _seed(f"Terrible Herbst {tag}", "convenience_store", "200 Hwy 95, Lake Havasu City"),
        _seed(f"Gas Co {tag}", "gas_station", "300 Hwy 95, Lake Havasu City"),
    ]
    try:
        with SessionLocal() as s:
            pool = gas_prices._load_gas_station_providers(s)
        names = {p.provider_name for p in pool}
        assert f"Pilot Travel Center {tag}" in names
        assert f"Terrible Herbst {tag}" in names
        assert f"Gas Co {tag}" in names
    finally:
        _cleanup(ids)


def test_match_links_truck_stop_provider() -> None:
    """A GasBuddy 'Pilot' station deep-links to the truck_stop provider row."""
    tag = uuid.uuid4().hex[:8]
    ids = [_seed(f"Pilot Travel Center {tag}", "truck_stop", "100 Hwy 95, Lake Havasu City")]
    try:
        with SessionLocal() as s:
            pool = gas_prices._load_gas_station_providers(s)
            station = {"name": f"Pilot Travel Center {tag}", "brand": "Pilot",
                       "address": "100 Hwy 95, Lake Havasu City"}
            match = gas_prices._match_provider(station, pool)
            assert match is not None
            assert match.provider_name == f"Pilot Travel Center {tag}"
    finally:
        _cleanup(ids)


# -- DL-17: per-station link gating (confident name+street, else UNLINKED) ----


def test_name_only_match_does_not_link() -> None:
    """A name hit WITHOUT an agreeing street number is not confident -> None.

    This is the both-Maverik bug: a station whose street differs from the
    provider row must render UNLINKED rather than wrong-linked.
    """
    tag = uuid.uuid4().hex[:8]
    ids = [_seed(f"Maverik {tag}", "convenience_store", "100 Acoma Blvd, Lake Havasu City")]
    try:
        with SessionLocal() as s:
            pool = gas_prices._load_gas_station_providers(s)
            # Same brand, DIFFERENT street -> a second physical Maverik station.
            station = {"name": f"Maverik {tag}", "brand": "Maverik",
                       "address": "2500 N McCulloch Blvd, Lake Havasu City"}
            assert gas_prices._match_provider(station, pool) is None
    finally:
        _cleanup(ids)


def test_station_without_street_number_is_unlinked() -> None:
    """No station street number -> we can't confirm which station it is -> None."""
    tag = uuid.uuid4().hex[:8]
    ids = [_seed(f"Maverik {tag}", "convenience_store", "100 Acoma Blvd, Lake Havasu City")]
    try:
        with SessionLocal() as s:
            pool = gas_prices._load_gas_station_providers(s)
            station = {"name": f"Maverik {tag}", "brand": "Maverik",
                       "address": "Acoma Blvd, Lake Havasu City"}  # no leading number
            assert gas_prices._match_provider(station, pool) is None
    finally:
        _cleanup(ids)


def test_two_brand_stations_do_not_both_link_to_one_provider() -> None:
    """Two physical Maverik stations + one Maverik provider row: only the
    station whose street agrees links; the other renders unlinked."""
    tag = uuid.uuid4().hex[:8]
    ids = [_seed(f"Maverik {tag}", "convenience_store", "100 Acoma Blvd, Lake Havasu City")]
    try:
        with SessionLocal() as s:
            pool = gas_prices._load_gas_station_providers(s)
            same_street = {"name": f"Maverik {tag}", "brand": "Maverik",
                           "address": "100 Acoma Blvd, Lake Havasu City"}
            other_street = {"name": f"Maverik {tag}", "brand": "Maverik",
                            "address": "2500 N McCulloch Blvd, Lake Havasu City"}
            assert gas_prices._match_provider(same_street, pool) is not None
            assert gas_prices._match_provider(other_street, pool) is None
    finally:
        _cleanup(ids)
