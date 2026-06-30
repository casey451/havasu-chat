"""F14: drop the unreliable auto-scraped Google photo for trade categories
(home services, professional services, auto) so a plumber never shows a kite —
while keeping owner-uploaded / pinned photos and every photo-meaningful category."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.providers import queries


def _stub(category: str, *, pinned: str | None = None) -> SimpleNamespace:
    attrs = {"hero_pin_photo_url": pinned} if pinned else {}
    return SimpleNamespace(category=category, attributes=attrs, entity=None)


def test_trade_category_suppresses_google_hero() -> None:
    with patch.object(queries, "first_renderable_google_photo", return_value="/static/biz-photos/x.jpg"):
        # Trades -> no Google photo (branded placeholder shows instead).
        assert queries.derive_hero_photo(_stub("home_services")) is None
        assert queries.derive_hero_photo(_stub("professional_services")) is None
        assert queries.derive_hero_photo(_stub("auto")) is None
        # Photo-meaningful categories keep their Google photo.
        assert queries.derive_hero_photo(_stub("food_drink")) == "/static/biz-photos/x.jpg"
        assert queries.derive_hero_photo(_stub("lodging")) == "/static/biz-photos/x.jpg"
        assert queries.derive_hero_photo(_stub("retail")) == "/static/biz-photos/x.jpg"
        # A curated PINNED hero is kept even for a trade (owner intent wins).
        assert queries.derive_hero_photo(_stub("home_services", pinned="/pin.jpg")) == "/pin.jpg"


def test_trade_category_suppresses_google_gallery() -> None:
    with patch.object(queries, "iter_renderable_google_photos", return_value=iter(["/g1.jpg"])):
        assert queries.derive_gallery(_stub("home_services"), exclude_hero=False) == []
    with patch.object(queries, "iter_renderable_google_photos", return_value=iter(["/g1.jpg"])):
        assert queries.derive_gallery(_stub("food_drink"), exclude_hero=False) == ["/g1.jpg"]


def test_google_photos_allowed_predicate() -> None:
    assert queries._google_photos_allowed(_stub("home_services")) is False
    assert queries._google_photos_allowed(_stub("auto")) is False
    assert queries._google_photos_allowed(_stub("food_drink")) is True
    assert queries._google_photos_allowed(_stub("")) is True  # unknown -> keep
