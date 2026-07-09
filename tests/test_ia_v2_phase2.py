"""IA v2 (Phase 2) — unit tests for label unification, cross-surface config, and
the "best match" default leaf sort. Pure-function tests; no DB required.
"""

from __future__ import annotations

from app.categories.cross_surface import CROSS_SURFACE
from app.categories.display_labels import display_label
from app.categories.router import _apply_list_controls


# ── Slice 1: display labels ────────────────────────────────────────────────
def test_display_label_overrides() -> None:
    assert display_label("on-the-water", "On the Water") == "Lake & Boating"
    assert display_label("family-and-education", "Family & Education") == "For Kids & Families"
    assert display_label("beauty-and-personal-care", "Beauty & Personal Care") == "Salons & Spas"
    assert display_label("auto-rv-and-marine", "Auto, RV & Marine") == "Auto & Boat Service"


def test_display_label_fallback_to_db_name() -> None:
    # Departments with no override keep their live Category.name.
    assert display_label("eat-and-drink", "Eat & Drink") == "Eat & Drink"
    assert display_label("health-and-medical", "Health & Medical") == "Health & Medical"


def test_display_label_last_resort_titlecase() -> None:
    assert display_label("some-future-dept") == "Some Future Dept"


# ── Slice 2: cross-surface config integrity ────────────────────────────────
def test_cross_surface_shape() -> None:
    for host, sections in CROSS_SURFACE.items():
        assert isinstance(host, str) and host
        for section in sections:
            assert section["heading"]
            assert section["leaves"]
            for ref in section["leaves"]:
                assert len(ref) == 2  # (source_department_slug, leaf_slug)
                assert all(isinstance(x, str) and x for x in ref)


def test_cross_surface_covers_boater_and_family() -> None:
    # The two flagship fixes from the walkthrough.
    headings = {s["heading"] for s in CROSS_SURFACE["on-the-water"]}
    assert "Boat services" in headings
    family_headings = {s["heading"] for s in CROSS_SURFACE["family-and-education"]}
    assert "Classes & lessons" in family_headings


def test_cross_surface_covers_tattoo() -> None:
    # P7 polish: the single-leaf tattoo department surfaces self-care neighbors.
    headings = {s["heading"] for s in CROSS_SURFACE["tattoo"]}
    assert "Salons & self-care" in headings
    leaves = {ref for s in CROSS_SURFACE["tattoo"] for ref in s["leaves"]}
    assert ("beauty-and-personal-care", "med-spas-and-aesthetics") in leaves


# ── Slice 3: best-match default leaf sort ──────────────────────────────────
def _card(name: str, *, is_open=None, has_reviews=False, is_sponsored=False) -> dict:
    return {
        "name": name,
        "is_open": is_open,
        "has_reviews": has_reviews,
        "is_sponsored": is_sponsored,
    }


def test_best_match_demotes_closed_and_unreviewed() -> None:
    cards = [
        _card("Closed NoRev", is_open=False, has_reviews=False),
        _card("Open Reviewed", is_open=True, has_reviews=True),
        _card("Open NoRev", is_open=True, has_reviews=False),
        _card("Closed Reviewed", is_open=False, has_reviews=True),
    ]
    visible, controls = _apply_list_controls({}, cards, base_path="/categories/x/y")
    order = [c["name"] for c in visible]
    assert order[0] == "Open Reviewed"
    assert order[-1] == "Closed NoRev"
    assert controls["sort"] == "top"


def test_best_match_keeps_sponsored_pinned_on_top() -> None:
    cards = [
        _card("Open Reviewed", is_open=True, has_reviews=True),
        _card("Sponsored Closed", is_open=False, has_reviews=False, is_sponsored=True),
    ]
    visible, _ = _apply_list_controls({}, cards, base_path="/x")
    assert visible[0]["name"] == "Sponsored Closed"


def test_az_sort_unaffected() -> None:
    cards = [
        _card("Zebra", is_open=True, has_reviews=True),
        _card("Apple", is_open=False, has_reviews=False),
    ]
    visible, _ = _apply_list_controls({"sort": "az"}, cards, base_path="/x")
    assert [c["name"] for c in visible] == ["Apple", "Zebra"]
