"""Phase 5 — osm_overpass_load script."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Provider
from scripts.osm_overpass_load import ingest_rows


def test_osm_overpass_load_filters_wrapper_elements(tmp_path: Path) -> None:
    wrapper = {
        "elements": [
            {"type": "node", "id": 1, "lat": 34.5, "lon": -114.35, "tags": {"leisure": "marina", "name": "A"}},
            {"type": "node", "id": 2, "lat": 34.51, "lon": -114.36, "tags": {"natural": "tree"}},
        ]
    }
    p = tmp_path / "osm.jsonl"
    p.write_text(json.dumps(wrapper) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = ingest_rows(rows, tag="leisure", value="marina", category_slug="on-the-water", dry_run=True)
    assert counts["elements_seen"] == 1
    assert counts["payloads_ready"] == 1


def test_osm_overpass_load_inserts_provider(tmp_path: Path) -> None:
    uid = uuid.uuid4().hex[:10]
    name = f"OSM Test Marina {uid}"
    row = {
        "type": "node",
        "id": 4242,
        "lat": 34.101,
        "lon": -113.801,
        "tags": {"leisure": "marina", "name": name},
    }
    p = tmp_path / "osm2.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = ingest_rows(
        rows,
        tag="leisure",
        value="marina",
        category_slug="on-the-water",
        dry_run=False,
    )
    assert counts["inserted"] == 1

    with SessionLocal() as db:
        q = select(Provider).where(Provider.provider_name == name)
        prov = db.scalars(q).first()
        assert prov is not None
        assert prov.source == "osm"
