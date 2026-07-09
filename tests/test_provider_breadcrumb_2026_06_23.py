"""Provider breadcrumb — label and href derive from the SAME category source.

Phase 2.1 (FIX_SPEC_2026-06-23). Live bug: Bridge City Combat showed the
subcategory label "Kids' Classes & Camps" (from its entity category) but the
breadcrumb LINKED to ``/categories/health-and-medical`` (from the legacy
``provider.category`` column). Label and link must agree.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.providers.queries import category_label_for
from app.providers.view_models import _category_url_for


def _cat(slug: str, name: str, parent: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(slug=slug, name=name, parent=parent)


def _provider_with_entity_category(cat: SimpleNamespace, *, legacy: str) -> SimpleNamespace:
    ec = SimpleNamespace(category=cat, is_primary=True, id=1)
    entity = SimpleNamespace(categories=[ec])
    return SimpleNamespace(
        entity=entity, category=legacy, category_ref=None, primary_category=None
    )


def test_leaf_entity_category_label_and_url_agree() -> None:
    dept = _cat("family-and-education", "Family & Education")
    leaf = _cat("kids-classes-and-camps", "Kids' Classes & Camps", parent=dept)
    # Legacy column points somewhere ELSE entirely (the live divergence).
    prov = _provider_with_entity_category(leaf, legacy="health_medical")

    assert category_label_for(prov) == "Kids' Classes & Camps"
    url = _category_url_for(prov)
    # Href links the SAME (leaf) category the label names — not the legacy column.
    assert url == "/categories/family-and-education/kids-classes-and-camps"
    assert "health-and-medical" not in url


def test_department_entity_category_links_department_page() -> None:
    dept = _cat("eat-and-drink", "Eat & Drink")  # no parent → department
    prov = _provider_with_entity_category(dept, legacy="totally_made_up")
    assert category_label_for(prov) == "Eat & Drink"
    assert _category_url_for(prov) == "/categories/eat-and-drink"


def test_legacy_only_provider_still_resolves_via_legacy_path() -> None:
    """No entity categories → unchanged legacy behavior (regression guard for the
    existing ``_category_url_for`` contract)."""
    rest = SimpleNamespace(category="restaurant")
    assert _category_url_for(rest) == "/categories/eat-and-drink"
    assert _category_url_for(SimpleNamespace(category=None)) == "/categories"
