"""Phase 4c — Lake Ink & Brass business portal.

The funnel (/portal) and the claim entry (/portal/claim) are public and render
on an empty DB, so they go through the real route (TestClient). The three
merchant dashboards (placements / buy-a-placement / creatives) are auth-gated, so
their templates are rendered directly with sample context. Asserts: flag-swap +
desert default, the noindex split (funnel/claim indexable; dashboards noindex),
single-h1, structural a11y, the preserved autocomplete JS, and — critically —
that every billing/creative form keeps its exact field names + actions.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.main import app
from app.portal.router import templates as _portal_templates


def _req(path: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def _render(name: str, path: str, **ctx: object) -> str:
    return _portal_templates.env.get_template(name).render(request=_req(path), **ctx)


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


class _Prov:
    def __init__(self, pid: str, name: str, category: str | None = None) -> None:
        self.id = pid
        self.provider_name = name
        self.category = category


class _Placement:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)


# ── public funnel + claim (full route, empty DB) ────────────────────────────

def test_lake_portal_funnel() -> None:
    b = TestClient(app).get("/portal?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_redesign.css" in b
    assert 'name="robots" content="noindex"' not in b  # public funnel is indexable
    assert 'href="/portal/claim"' in b and 'href="/portal/placements"' in b
    assert "Rankings aren't for sale" in b  # honest brand card (no fabricated metrics)
    assert "38k" not in b and "12k" not in b  # mockup's illustrative stats omitted
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_portal_claim_preserves_autocomplete() -> None:
    b = TestClient(app).get("/portal/claim?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_redesign.css" in b  # v4.6 PR-1: v4 shell
    assert 'name="robots" content="noindex"' not in b  # public, indexable
    assert 'id="claim-search-q"' in b and 'id="claim-search-results"' in b  # JS hooks
    assert "/api/search/suggestions" in b  # autocomplete preserved verbatim
    assert 'action="/chat"' in b and 'role="search"' in b
    assert b.count("<h1") == 1
    assert not _a11y(b)


# ── merchant placements dashboard (direct render) ───────────────────────────

def test_lake_placements_empty_and_populated() -> None:
    empty = _render("portal_placements_lake.html", "/portal/placements",
                    providers=[], placements=[], prov_by_id={}, type_labels={},
                    purchased=False)
    assert 'name="robots" content="noindex"' in empty  # dashboards are noindex
    assert "No claimed listings yet" in empty
    assert 'href="/portal/claim"' in empty
    assert empty.count("<h1") == 1
    assert not _a11y(empty)

    prov = _Prov("prov-1", "Barley Brothers", "Brewpub")
    pl = _Placement(provider_id="prov-1", placement_type="homepage_rotating",
                    category_slug=None, rank_tier=None, billing_type="monthly",
                    price_cents=1500, status="active")
    full = _render("portal_placements_lake.html", "/portal/placements",
                   providers=[prov], placements=[pl], prov_by_id={"prov-1": prov},
                   type_labels={"homepage_rotating": "Homepage rotating"},
                   purchased=True)
    assert "Barley Brothers" in full
    assert "Homepage rotating" in full
    assert "$15" in full  # price formatted from cents
    assert "Request received." in full  # purchased banner
    assert 'href="/portal/placements/new?provider_id=prov-1"' in full
    assert full.count("<h1") == 1
    assert not _a11y(full)


# ── buy-a-placement form (direct render) ────────────────────────────────────

_TYPES = {
    "homepage_rotating": {"label": "Homepage rotating", "blurb": "A spot in the homepage bar."},
    "category_rank": {"label": "Category ranking", "blurb": "A sticky tier in a category."},
    "page_ad": {"label": "Page ad", "blurb": "One ad slot on a category page."},
}
_PRICES = {"homepage_rotating": 1500, "page_ad": 1000,
           "category_rank": {1: 5000, 2: 4000, 3: 3000, 4: 2000, 5: 1000}}


def test_lake_placement_new_form_and_errors() -> None:
    prov = _Prov("prov-1", "Barley Brothers")
    clean = _render("portal_placement_new_lake.html", "/portal/placements/new",
                    providers=[prov], selected_provider_id="", categories=[("eat-drink", "Eat & Drink")],
                    types=_TYPES, prices=_PRICES,
                    creatives=[{"id": "c1", "provider_name": "Barley Brothers", "headline": "Sunset cruises"}],
                    errors={}, form={})
    assert 'name="robots" content="noindex"' in clean
    assert 'action="/portal/placements/new"' in clean
    # every billing field name must survive the reskin
    for field in ("provider_id", "placement_type", "category_slug", "rank_tier",
                  "creative_id", "billing_type"):
        assert f'name="{field}"' in clean
    assert 'value="homepage_rotating"' in clean and 'value="recurring"' in clean
    assert "$15/mo" in clean  # indicative price rendered
    assert clean.count("<h1") == 1
    assert not _a11y(clean)

    errored = _render("portal_placement_new_lake.html", "/portal/placements/new",
                      providers=[prov], selected_provider_id="", categories=[("eat-drink", "Eat & Drink")],
                      types=_TYPES, prices=_PRICES, creatives=[],
                      errors={"provider_id": "Pick a listing.", "placement_type": "Choose a type."},
                      form={"provider_id": "", "placement_type": "", "category_slug": "",
                            "rank_tier": "", "billing_type": "monthly", "creative_id": ""})
    assert "Please fix the highlighted fields" in errored  # error summary
    assert 'href="#provider_id"' in errored  # summary links to the field
    assert "Pick a listing." in errored
    assert not _a11y(errored)


# ── ad creatives form (direct render) ───────────────────────────────────────

def test_lake_creatives_form_and_errors() -> None:
    prov = _Prov("prov-1", "Barley Brothers")
    clean = _render("portal_creatives_lake.html", "/portal/creatives",
                    providers=[prov], creatives=[], errors={}, form={})
    assert 'name="robots" content="noindex"' in clean
    assert 'enctype="multipart/form-data"' in clean  # file upload preserved
    for field in ("provider_id", "headline", "body", "image_url",
                  "image_url_mobile", "image_file", "cta_label", "cta_url"):
        assert f'name="{field}"' in clean
    assert 'accept="image/png,image/jpeg,image/webp,image/gif"' in clean
    assert "None yet" in clean  # empty gallery
    assert clean.count("<h1") == 1
    assert not _a11y(clean)

    errored = _render("portal_creatives_lake.html", "/portal/creatives",
                      providers=[prov],
                      creatives=[{"id": "c1", "provider_id": "prov-1",
                                  "provider_name": "Barley Brothers",
                                  "headline": "Sunset cruises", "image_url": None}],
                      errors={"headline": "Give the creative a headline or an image."},
                      form={"provider_id": "prov-1"})
    assert "Please fix the highlighted fields" in errored
    assert "Sunset cruises" in errored  # existing creative listed
    assert not _a11y(errored)
