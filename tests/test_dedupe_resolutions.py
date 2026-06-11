"""Track B1 dedupe: resolution paths, queue persistence, merge 301, ingest gate.

Covers the B1 additions around the duplicate review queue:

  * resolve endpoints (not_duplicate / multi_location / parent_child) persist a
    DedupeResolution row and the pair stops surfacing on the queue page;
  * multi_location stamps a shared ``Provider.location_group_id`` and the
    profile sibling query returns the cross-link;
  * parent_child stamps ``Provider.parent_provider_id`` and the parent page
    query returns the child (and the cycle guard 400s);
  * merging stamps ``attributes.merged_into_slug`` (provider route 301s) and
    records a ``merged`` resolution;
  * google_place_id gap-fill MOVES the value off the loser (the
    ux_providers_google_place_id partial unique index would otherwise break);
  * the ingest reconciler matches a payload's place_id against
    ``Provider.google_place_id`` even when no Location row carries it;
  * the batch place_id merge script skips human-resolved pairs.

Same conventions as test_admin_provider_merge_review.py: routes commit, so
every test cleans up its rows (providers, entities, resolutions) in finally.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.contrib.ingest_base import EntityPayload
from app.contrib.ingest_reconciler import reconcile_hit
from app.contrib.provider_merge import merge_providers
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import DedupeResolution, Entity, Provider, dedupe_pair_key
from app.db.seed_helpers import derive_provider_slug
from app.main import app
from app.providers import queries as provider_queries

_LAT = 34.4839
_LNG = -114.3225


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


@pytest.fixture
def admin_client() -> TestClient:
    client = TestClient(app)
    client.cookies.clear()
    _login(client)
    return client


def _make_pair(name: str, *, place_ids: tuple[str | None, str | None] = (None, None)) -> tuple[str, str]:
    """Two live same-name providers at one point -> a geo+name candidate pair."""
    with SessionLocal() as s:
        ids = []
        for pid in place_ids:
            p = Provider(
                provider_name=name,
                category="eat-drink",
                slug=derive_provider_slug(s, name),
                source="go_lake_havasu",
                lat=_LAT,
                lng=_LNG,
                draft=False,
                is_active=True,
                google_place_id=pid,
            )
            s.add(p)
            create_provider_and_entity(s, p)
            s.flush()
            ids.append(p.id)
        s.commit()
        return ids[0], ids[1]


def _cleanup(name: str) -> None:
    with SessionLocal() as s:
        provs = s.scalars(select(Provider).where(Provider.provider_name == name)).all()
        ent_ids = [p.entity_id for p in provs if p.entity_id]
        prov_ids = [p.id for p in provs]
        for p in provs:
            p.parent_provider_id = None  # break self-FK before delete
        s.flush()
        for p in provs:
            s.delete(p)
        s.flush()
        for ent in s.scalars(select(Entity).where(Entity.id.in_(ent_ids))).all():
            s.delete(ent)
        for res in s.scalars(select(DedupeResolution)).all():
            if res.provider_id_a in prov_ids or res.provider_id_b in prov_ids:
                s.delete(res)
        s.commit()


def test_resolve_not_duplicate_persists_and_hides_pair(admin_client):
    name = f"Resolve NotDup {uuid.uuid4().hex[:8]}"
    a, b = _make_pair(name)
    try:
        resp = admin_client.get("/admin/providers/duplicates")
        assert name in resp.text

        resp = admin_client.post(
            "/admin/providers/duplicates/resolve",
            data={"keep_id": a, "dup_id": b, "resolution": "not_duplicate",
                  "reason": "geo+name"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        with SessionLocal() as s:
            row = s.scalar(
                select(DedupeResolution).where(
                    DedupeResolution.pair_key == dedupe_pair_key(a, b)
                )
            )
            assert row is not None
            assert row.resolution == "not_duplicate"
            assert row.reason == "geo+name"

        # The pair no longer surfaces on the queue page.
        resp = admin_client.get("/admin/providers/duplicates")
        assert name not in resp.text
    finally:
        _cleanup(name)


def test_resolve_multi_location_links_siblings(admin_client):
    name = f"Resolve MultiLoc {uuid.uuid4().hex[:8]}"
    a, b = _make_pair(name)
    try:
        resp = admin_client.post(
            "/admin/providers/duplicates/resolve",
            data={"keep_id": a, "dup_id": b, "resolution": "multi_location"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        with SessionLocal() as s:
            pa, pb = s.get(Provider, a), s.get(Provider, b)
            assert pa.location_group_id
            assert pa.location_group_id == pb.location_group_id
            # Both stay live — multi-location is keep-both by definition.
            assert pa.is_active and pb.is_active
            siblings = provider_queries.sibling_locations(s, pa)
            assert [c["url"] for c in siblings] == [f"/provider/{pb.slug}"]
    finally:
        _cleanup(name)


def test_resolve_parent_child_and_cycle_guard(admin_client):
    name = f"Resolve ParentChild {uuid.uuid4().hex[:8]}"
    a, b = _make_pair(name)
    try:
        resp = admin_client.post(
            "/admin/providers/duplicates/resolve",
            data={"keep_id": a, "dup_id": b, "resolution": "parent_child",
                  "parent_id": a},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        with SessionLocal() as s:
            pa, pb = s.get(Provider, a), s.get(Provider, b)
            assert pb.parent_provider_id == a
            children = provider_queries.department_children(s, pa)
            assert [c["url"] for c in children] == [f"/provider/{pb.slug}"]
            up = provider_queries.parent_org_link(s, pb)
            assert up is not None and up["url"] == f"/provider/{pa.slug}"

        # Reversing direction would make a cycle -> 400.
        resp = admin_client.post(
            "/admin/providers/duplicates/resolve",
            data={"keep_id": a, "dup_id": b, "resolution": "parent_child",
                  "parent_id": b},
        )
        assert resp.status_code == 400
    finally:
        _cleanup(name)


def test_resolve_validates_inputs(admin_client):
    name = f"Resolve BadInput {uuid.uuid4().hex[:8]}"
    a, b = _make_pair(name)
    try:
        for data in (
            {"keep_id": a, "dup_id": b, "resolution": "nonsense"},
            {"keep_id": a, "dup_id": a, "resolution": "not_duplicate"},
            {"keep_id": a, "dup_id": b, "resolution": "parent_child", "parent_id": "zzz"},
        ):
            resp = admin_client.post("/admin/providers/duplicates/resolve", data=data)
            assert resp.status_code == 400
        resp = admin_client.post(
            "/admin/providers/duplicates/resolve",
            data={"keep_id": a, "dup_id": "no-such-id", "resolution": "not_duplicate"},
        )
        assert resp.status_code == 404
    finally:
        _cleanup(name)


def test_merge_stamps_redirect_records_resolution_and_moves_place_id(admin_client):
    name = f"Merge Stamp {uuid.uuid4().hex[:8]}"
    pid = f"ChIJtest{uuid.uuid4().hex[:12]}"
    # keep has NO place_id; dup has one -> gap-fill must MOVE it.
    a, b = _make_pair(name, place_ids=(None, pid))
    try:
        with SessionLocal() as s:
            keep_slug = s.get(Provider, a).slug
            dup_slug = s.get(Provider, b).slug

        resp = admin_client.post(
            "/admin/providers/duplicates/merge",
            data={"keep_id": a, "dup_id": b},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        with SessionLocal() as s:
            keep, dup = s.get(Provider, a), s.get(Provider, b)
            # 301 stamp written by the primitive now (not just the batch script).
            assert (dup.attributes or {}).get("merged_into_slug") == keep_slug
            # place_id moved, not copied (partial unique index safety).
            assert keep.google_place_id == pid
            assert dup.google_place_id is None
            # merged resolution recorded -> pair never resurfaces.
            row = s.scalar(
                select(DedupeResolution).where(
                    DedupeResolution.pair_key == dedupe_pair_key(a, b)
                )
            )
            assert row is not None and row.resolution == "merged"

        # The retired slug 301s to the survivor on the public route.
        public = TestClient(app)
        resp = public.get(f"/provider/{dup_slug}", follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == f"/provider/{keep_slug}"
    finally:
        _cleanup(name)


def test_merge_repoints_department_children():
    name = f"Merge Reparent {uuid.uuid4().hex[:8]}"
    a, b = _make_pair(name)
    child_name = f"{name} Dept"
    with SessionLocal() as s:
        child = Provider(
            provider_name=child_name,
            category="eat-drink",
            slug=derive_provider_slug(s, child_name),
            source="go_lake_havasu",
            draft=False,
            is_active=True,
            parent_provider_id=b,  # child of the row about to be merged away
        )
        s.add(child)
        create_provider_and_entity(s, child)
        s.commit()
        child_id = child.id
    try:
        with SessionLocal() as s:
            result = merge_providers(s, keep_id=a, dup_id=b, dry_run=False)
            s.commit()
            assert result.repointed.get("providers.parent_provider_id") == 1
        with SessionLocal() as s:
            assert s.get(Provider, child_id).parent_provider_id == a
    finally:
        _cleanup(child_name)
        _cleanup(name)


def test_reconciler_matches_provider_level_place_id():
    name = f"Gate ProviderPid {uuid.uuid4().hex[:8]}"
    pid = f"ChIJgate{uuid.uuid4().hex[:12]}"
    a, _b = _make_pair(name, place_ids=(pid, None))
    try:
        with SessionLocal() as s:
            prov = s.get(Provider, a)
            # Ensure the Location row does NOT carry the place_id (the gap the
            # gate closes): provider-level only.
            loc = prov.entity.location if prov.entity else None
            if loc is not None:
                loc.google_place_id = None
                s.commit()
            payload = EntityPayload(
                name="Totally Different Name",
                entity_type="provider",
                google_place_id=pid,
                source="google_places",
            )
            result = reconcile_hit(s, payload)
            assert result.action == "update"
            assert result.existing_id == prov.entity_id
            assert "provider row" in (result.reason or "")
    finally:
        _cleanup(name)


def test_batch_place_id_script_skips_resolved_pairs():
    from sqlalchemy import text

    from scripts.merge_place_id_duplicates import run

    name = f"Batch PlaceId {uuid.uuid4().hex[:8]}"
    pid = f"ChIJbatch{uuid.uuid4().hex[:12]}"
    # The partial unique index ux_providers_google_place_id reaches the SQLite
    # test DB too (sqlite_where in the e9f0 migration), so a same-place_id pair
    # cannot exist while it stands — which is the point of the batch script:
    # it exists for the day that index is bypassed or missing. Simulate exactly
    # that broken state by dropping the index in this throwaway test DB.
    with SessionLocal() as s:
        s.execute(text("DROP INDEX IF EXISTS ux_providers_google_place_id"))
        s.commit()
    a, b = _make_pair(name, place_ids=(pid, pid))
    try:
        with SessionLocal() as s:
            counts = run(session=s)  # dry run
            assert counts["pairs"] == 1
            assert counts["merged"] == 0
            # Both rows untouched by the dry run.
            assert s.get(Provider, a).is_active and s.get(Provider, b).is_active

        # A human resolution outranks the machine tier.
        with SessionLocal() as s:
            lo, hi = sorted((a, b))
            s.add(
                DedupeResolution(
                    pair_key=dedupe_pair_key(a, b),
                    provider_id_a=lo,
                    provider_id_b=hi,
                    resolution="multi_location",
                )
            )
            s.commit()
        with SessionLocal() as s:
            counts = run(session=s)
            assert counts["pairs"] == 0
            assert counts["skipped_resolved"] == 1
    finally:
        _cleanup(name)
