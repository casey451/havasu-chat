"""Lake Ink & Brass — /search keyword results page theme-select.

The concierge falls through to /search for descriptive queries, so /search must
follow the active theme (it was desert-only before). One check per theme, plus
the noindex/indexable split (results pages noindex, the bare form indexable).
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Provider
from app.main import app


def test_search_lake_theme_select() -> None:
    # A keyword query WITH a match renders the lake results page. (F13 routes
    # zero-result / question queries to the AI, so seed a hit to land on /search.)
    suf = uuid.uuid4().hex[:10]
    mark = f"Brasswork Bindery {suf}"
    slug = f"brasswork-bindery-{suf}"
    with SessionLocal() as db:
        ent = Entity(
            id=str(uuid.uuid4()), entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=slug, name=mark, description=mark, source="test-lake-search",
        )
        db.add(ent)
        db.flush()
        db.add(Provider(
            provider_name=mark, slug=slug, category="misc",
            source="test-lake-search", draft=False, is_active=True, entity_id=ent.id,
        ))
        db.commit()
    b = TestClient(app).get(f"/search?q={mark}&theme=lake")
    assert b.status_code == 200
    assert mark in b.text  # the results page rendered the row
    assert "/static/styles/lake_redesign.css" in b.text  # v4.6 PR-1: v4 shell
    assert 'data-theme="lake"' in b.text
    assert 'name="robots" content="noindex"' in b.text  # results page = noindex


def test_search_lake_blank_query_indexable() -> None:
    b = TestClient(app).get("/search?theme=lake")
    assert b.status_code == 200
    assert "/static/styles/lake_redesign.css" in b.text  # v4.6 PR-1: v4 shell
    assert 'name="robots" content="noindex"' not in b.text  # bare form stays indexable
