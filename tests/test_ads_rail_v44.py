"""v4.4 PR-5 — one paid unit + a rail that actually helps (Δ3/Δ5).

The marquee is the ONLY ad-shaped unit on home; the rail's ad placeholders and the
in-feed ad are gone, replaced by a Find-any-business launcher (live directory
counts) + a local-news card. The ticker is mobile-only.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.home import redesign
from app.main import app


def test_home_has_one_marquee_and_zero_ad_slots() -> None:
    with TestClient(app) as client:
        html = client.get("/home").text
    # Exactly one ad-shaped unit (the marquee), and no leftover ad placeholders.
    assert html.count("feature-marquee") == 1
    assert "feature-slot" not in html


def test_rail_is_the_launcher_not_ads() -> None:
    with TestClient(app) as client:
        html = client.get("/home").text
    assert "railcard" in html
    assert "Find any business" in html
    assert "All 16 categories" in html


# A representative index payload (the real /categories cache shape) so the mapping
# is tested without depending on seeded DB rows.
_FAKE_INDEX = [
    {"slug": "eat-and-drink", "count": 254},
    {"slug": "home-and-property-services", "count": 343},
    {"slug": "auto-rv-and-marine", "count": 322},
    {"slug": "health-and-medical", "count": 311},
    {"slug": "shopping-and-retail", "count": 241},
    {"slug": "beauty-and-personal-care", "count": 167},
    {"slug": "on-the-water", "count": 77},
    {"slug": "lodging", "count": 104},
    {"slug": "pets", "count": 45},  # a non-launcher dept still counts toward total
]


def test_launcher_maps_eight_categories_with_index_counts() -> None:
    with patch("app.categories.router._get_index_payload", return_value=_FAKE_INDEX):
        with SessionLocal() as db:
            launcher = redesign.directory_launcher(db)
    tiles = launcher["tiles"]
    # Exactly the 8 launcher categories, in the specced order, with short labels.
    assert [t["label"] for t in tiles] == [
        "Eat & Drink", "Home Services", "Auto & Boat", "Health",
        "Shopping", "Salons", "Lake & Boating", "Lodging",
    ]
    # Counts come straight from the directory index (never fabricated).
    by_label = {t["label"]: t for t in tiles}
    assert by_label["Eat & Drink"]["count"] == 254
    assert by_label["Lodging"]["count"] == 104
    assert by_label["Eat & Drink"]["url"] == "/categories/eat-and-drink"
    # Total sums ALL departments (incl. non-launcher), floor-rounded hundreds.
    assert launcher["total_raw"] == sum(r["count"] for r in _FAKE_INDEX)  # 1864
    assert launcher["total"] == "1,800+"


def test_launcher_omits_a_missing_category() -> None:
    partial = [r for r in _FAKE_INDEX if r["slug"] != "lodging"]
    with patch("app.categories.router._get_index_payload", return_value=partial):
        with SessionLocal() as db:
            launcher = redesign.directory_launcher(db)
    assert all(t["label"] != "Lodging" for t in launcher["tiles"])  # honest omission
    assert len(launcher["tiles"]) == 7


def test_news_card_and_ticker_omitted_when_empty() -> None:
    empty = SimpleNamespace(items=[])
    with patch("app.home.router.news_store.ticker_view", return_value=empty):
        with TestClient(app) as client:
            html = client.get("/home").text
    # Honest omission: no news card, no ticker when the pull is empty.
    assert "newscard" not in html
    assert "newsbar" not in html
    # ...but the launcher still renders (it doesn't depend on news).
    assert "railcard" in html
