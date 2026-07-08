"""WS9a: curated cuisine override + enum additions (Casey, 2026-07-08)."""

from __future__ import annotations

from app.categories.subcategories import (
    cuisine_label,
    cuisine_slugs_in_order,
    derive_cuisine,
    effective_cuisine,
)


def test_curated_attribute_wins_over_derivation() -> None:
    # A name-only classification: Google types carry no cuisine token, so the
    # derivation is None, but the curated backfill value surfaces.
    assert derive_cuisine("restaurant", ["point_of_interest"]) is None
    assert effective_cuisine({"cuisine": "mexican"}, "restaurant", ["point_of_interest"]) == "mexican"


def test_invalid_or_missing_curated_falls_back_to_derivation() -> None:
    assert effective_cuisine({"cuisine": "not_a_cuisine"}, "sushi_restaurant", None) == "japanese"
    assert effective_cuisine({}, "sushi_restaurant", None) == "japanese"
    assert effective_cuisine(None, "sushi_restaurant", None) == "japanese"
    assert effective_cuisine(None, "restaurant", None) is None  # honest unknown


def test_curated_cannot_invent_an_unknown_cuisine() -> None:
    # Only known enum slugs are honored; junk is ignored, not surfaced.
    assert effective_cuisine({"cuisine": "klingon"}, None, None) is None


def test_enum_additions_classify_from_google_type() -> None:
    assert derive_cuisine("korean_restaurant", None) == "korean"
    assert derive_cuisine("cuban_restaurant", None) == "cuban"
    assert derive_cuisine("chicken_restaurant", None) == "fried_chicken"
    for slug in ("korean", "cuban", "fried_chicken"):
        assert slug in cuisine_slugs_in_order()
        assert cuisine_label(slug) is not None


def test_specific_cuisine_still_wins_over_new_generic_additions() -> None:
    # A place typed both mexican and chicken stays mexican (enum order precedence).
    assert derive_cuisine("mexican_restaurant", ["chicken_restaurant"]) == "mexican"


def test_apply_loader_skips_unknown_enum_slugs(tmp_path) -> None:
    from scripts.cuisine_backfill_apply import _load_approved

    p = tmp_path / "approved.csv"
    p.write_text(
        "slug,cuisine,note\ngood,mexican,x\nbad,klingon,x\nblank,,x\n", encoding="utf-8"
    )
    assert _load_approved(p) == [("good", "mexican")]
