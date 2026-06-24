"""Phase 3 — claim search, label parity, single-source count, brand titles.

FIX_SPEC_2026-06-23 §3.1–3.4.
"""

from __future__ import annotations

import re
import uuid

from fastapi.testclient import TestClient

from app.categories import router as cat_router
from app.categories.display_labels import (
    MAP_SCOPE_TO_DEPARTMENT,
    display_label,
    map_scope_label,
)
from app.categories.leaf_pages import all_departments
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.home import sandstone
from app.main import app

# ── 3.1 claim search → /claim/<slug> in one step ───────────────────────────────

def test_suggestions_expose_one_step_claim_url() -> None:
    name = f"Claimable Biz {uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        p = Provider(
            provider_name=name, category="eat_drink",
            verified=True, draft=False, is_active=True, pending_review=False,
            source="test-phase3-claim",
        )
        db.add(p)
        db.commit()
        entity_slug = db.query(Entity.slug).filter(Entity.id == p.entity_id).scalar()

    rows = TestClient(app).get(f"/api/search/suggestions?q={name[:14]}").json()
    match = next((r for r in rows if r["name"] == name), None)
    assert match is not None, "seeded commercial entity should surface in suggestions"
    # The claim flow resolves by ENTITY slug, so the one-step link uses it.
    assert match["claim_url"] == f"/claim/{entity_slug}"


def test_claim_page_links_results_to_claim_url() -> None:
    """Both claim templates send a search hit to claim_url (then the listing)."""
    for theme in ("lake", "desert"):
        html = TestClient(app).get(f"/portal/claim?theme={theme}").text
        assert "r.claim_url || r.url" in html, f"{theme} claim page not using claim_url"


# ── 3.2 category labels read identically across surfaces ────────────────────────

def test_map_scope_labels_match_directory_labels() -> None:
    with SessionLocal() as db:
        dir_labels = {
            dept.slug: display_label(dept.slug, dept.name)
            for dept, _l, _t in all_departments(db)
        }
    for scope, dept_slug in MAP_SCOPE_TO_DEPARTMENT.items():
        if dept_slug not in dir_labels:
            continue  # e.g. "events" — no directory department
        assert map_scope_label(scope) == dir_labels[dept_slug], (
            f"/map '{scope}' label {map_scope_label(scope)!r} != directory "
            f"'{dept_slug}' label {dir_labels[dept_slug]!r}"
        )


def test_specific_divergences_resolved() -> None:
    # The exact drifts called out in the audit.
    assert map_scope_label("on-the-water") == "Lake & Boating"      # was "Lake Life"
    assert map_scope_label("outdoors-parks-trails") == "Things to Do"  # was "Outdoors & Recreation"
    assert map_scope_label("classes-sports-recreation") == "Fitness & Classes"


# ── 3.3 category count single source (home "See all N" == directory list) ───────

def test_home_count_equals_directory_length() -> None:
    with SessionLocal() as db:
        home_tiles = sandstone.explore_tiles(db)
        cat_router.reset_index_cache()
        directory = cat_router._get_index_payload(db)
    assert len(home_tiles) == len(directory), (
        f"home shows 'See all {len(home_tiles)}' but directory lists {len(directory)}"
    )


# ── 3.4 brand titles end in "— Ask Hava" ───────────────────────────────────────

def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    assert m, "no <title>"
    return m.group(1).strip()


def test_legal_and_contribute_titles_end_in_ask_hava() -> None:
    client = TestClient(app)
    for path in ("/privacy", "/terms", "/contribute"):
        for theme in ("lake", "desert"):
            title = _title(client.get(f"{path}?theme={theme}").text)
            assert title.endswith("— Ask Hava"), f"{path} ({theme}) title = {title!r}"


def test_contribute_wordmark_is_ask_hava() -> None:
    html = TestClient(app).get("/contribute").text
    assert "<span>Ask Hava</span>" in html
    assert "Back to Ask Hava" in html
    assert "<span>Hava</span>" not in html  # the bare wordmark is gone
