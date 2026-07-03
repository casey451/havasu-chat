"""Direction C Eat & drink scroll row tests (PR D3).

Coverage:

1. ``queries_c.eat_row()`` shape and contract.
2. ``_load_eat_photos()`` file integrity + defensive fallback.
3. ``_format_rating`` rounding + no-zero discipline.
4. ``_build_eat_card`` shape.
5. End-to-end render via ``GET /home?redesign=1``:
   - Empty DB -> editorial empty-state bridge, no zero copy.
   - The scroll_row partial is included only when ``eat_cards`` populates.

The eat row's correctness when the DB has real data is exercised here
with mocked Provider objects (lightweight stand-ins) -- a populated-DB
integration test against a Postgres preview is out of scope for D3.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.home import queries_c
from app.main import app

# Phoenix is UTC-7 year-round (no DST). Pick a time mid-evening so an
# "Open until 10" restaurant counts as open and a 5am bakery counts as
# closed -- realistic spread for one snapshot.
_NOW_EVENING = datetime(2026, 5, 25, 19, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Constants / module-level invariants
# ---------------------------------------------------------------------------


def test_food_drink_categories_covers_legacy_labels() -> None:
    """The eat-row category filter must match every legacy ``Provider.category``
    string whose human label is "Eat & Drink" (queries.LEGACY_PROVIDER_CATEGORY_LABELS).
    Drift here would silently drop providers from the row."""
    from app.home.queries import LEGACY_PROVIDER_CATEGORY_LABELS

    legacy_food_drink = {
        slug for slug, label in LEGACY_PROVIDER_CATEGORY_LABELS.items() if label == "Eat & Drink"
    }
    eat_row_filter = set(queries_c._FOOD_DRINK_CATEGORIES)
    missing = legacy_food_drink - eat_row_filter
    assert not missing, (
        f"_FOOD_DRINK_CATEGORIES is missing {missing}; add to queries_c.py "
        f"or document the exclusion."
    )


def test_open_now_statuses_is_immutable() -> None:
    """The eat row's open-now filter is a frozenset so accidental mutation
    in a downstream module can't poison the filter at runtime."""
    assert isinstance(queries_c._OPEN_NOW_STATUSES, frozenset)
    assert queries_c._OPEN_NOW_STATUSES == frozenset({"open", "closing-soon"})


# ---------------------------------------------------------------------------
# Curated photo file integrity
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_curated_caches() -> None:
    queries_c.reset_cache()
    yield
    queries_c.reset_cache()


def test_curated_eat_photos_file_loads() -> None:
    """File exists, parses, and contains an ``photos`` mapping."""
    photos = queries_c._load_eat_photos()
    assert isinstance(photos, dict)
    assert photos, "expected at least one curated eat-row photo"
    for slug, url in photos.items():
        assert isinstance(slug, str) and slug
        assert isinstance(url, str)
        assert url.startswith("https://images.unsplash.com/"), (
            f"slug {slug!r} maps to a non-Unsplash URL: {url}"
        )
        assert "?w=" in url, f"slug {slug!r} URL is missing sizing params"


def test_load_eat_photos_missing_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Missing photo file must degrade to {} -- cards still render with
    the gradient placeholder, no 500."""
    bogus = tmp_path / "no_such_file.json"
    monkeypatch.setattr(queries_c, "_EAT_PHOTOS_PATH", bogus)
    queries_c.reset_cache()
    assert queries_c._load_eat_photos() == {}


def test_load_eat_photos_malformed_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Corrupt JSON -- still degrades to {}, never raises."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not: valid json", encoding="utf-8")
    monkeypatch.setattr(queries_c, "_EAT_PHOTOS_PATH", bad)
    queries_c.reset_cache()
    assert queries_c._load_eat_photos() == {}


def test_load_eat_photos_drops_non_string_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """A JSON-typo URL (null, number) is skipped; valid entries survive."""
    payload = tmp_path / "mixed.json"
    payload.write_text(
        '{"photos": {"good-slug": "https://images.unsplash.com/photo-x?w=600",'
        ' "bad-slug": null, "also-bad": 42, "empty": ""}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(queries_c, "_EAT_PHOTOS_PATH", payload)
    queries_c.reset_cache()
    photos = queries_c._load_eat_photos()
    assert photos == {"good-slug": "https://images.unsplash.com/photo-x?w=600"}


@pytest.mark.parametrize(
    "raw_json",
    [
        # Top-level is a list, not a dict -- legal JSON, wrong shape.
        '[{"photos": {"x": "https://example.com/x.jpg"}}]',
        # Top-level is a scalar.
        "42",
        '"a string at the root"',
        # Top-level is a dict but ``photos`` is not a mapping.
        '{"photos": 42}',
        '{"photos": ["a", "b"]}',
        '{"photos": "https://example.com/x.jpg"}',
    ],
)
def test_load_eat_photos_malformed_shape_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    raw_json: str,
) -> None:
    """Valid JSON of the wrong shape (top-level list, top-level scalar,
    or ``photos`` not a mapping) must degrade to ``{}`` rather than
    raise. A 500 on /home from a curator's JSON typo would be visible
    to every visitor."""
    payload = tmp_path / "wrong_shape.json"
    payload.write_text(raw_json, encoding="utf-8")
    monkeypatch.setattr(queries_c, "_EAT_PHOTOS_PATH", payload)
    queries_c.reset_cache()
    assert queries_c._load_eat_photos() == {}


# ---------------------------------------------------------------------------
# _format_rating
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (4.5, "4.5"),
        (4.0, "4.0"),
        (4.456, "4.5"),  # rounds to one decimal
        (3, "3.0"),
        (None, None),
        (0, None),  # no "0.0" rating per BUILD.md no-zero rule
        (0.0, None),
        (-1.2, None),
        ("not a number", None),
    ],
)
def test_format_rating(raw, expected) -> None:
    assert queries_c._format_rating(raw) == expected


# ---------------------------------------------------------------------------
# _build_eat_card shape
# ---------------------------------------------------------------------------


def test_build_eat_card_shape() -> None:
    fake = SimpleNamespace(
        slug="mudshark-brewing",
        provider_name="Mudshark Brewing",
        district="McCulloch Blvd",
        google_rating=4.5,
        google_review_count=128,
    )
    card = queries_c._build_eat_card(
        fake,
        status_class="open",
        status_text="Open until 10",
        image_url="https://example.com/img.jpg",
    )
    assert card == {
        "slug": "mudshark-brewing",
        "name": "Mudshark Brewing",
        "image_url": "https://example.com/img.jpg",
        "neighborhood": "McCulloch Blvd",
        "status": "open",
        "status_text": "Open until 10",
        "rating": "4.5",
        "review_count": 128,
    }


def test_build_eat_card_handles_missing_district_and_rating() -> None:
    fake = SimpleNamespace(
        slug=None,
        provider_name="Some Place",
        district=None,
        google_rating=None,
        google_review_count=None,
    )
    card = queries_c._build_eat_card(
        fake,
        status_class="closing-soon",
        status_text="Closes 9",
        image_url=None,
    )
    assert card["slug"] is None
    assert card["neighborhood"] == ""
    assert card["rating"] is None
    assert card["review_count"] is None
    assert card["image_url"] is None


def test_build_eat_card_hides_low_review_rating() -> None:
    """A high rating backed by too few reviews is hidden, not shown -- a
    1-review 5.0 reads as fake and floats junk to the top of the row."""
    thin = SimpleNamespace(
        slug="one-review-wonder",
        provider_name="One Review Wonder",
        district=None,
        google_rating=5.0,
        google_review_count=1,
    )
    card = queries_c._build_eat_card(thin, status_class="open", status_text="Open", image_url=None)
    assert card["rating"] is None
    assert card["review_count"] is None


def test_rating_display_gate() -> None:
    """``_rating_display`` shows a rating only at/above the review floor."""
    assert queries_c._rating_display(4.3, 1862) == ("4.3", 1862)
    assert queries_c._rating_display(5.0, 1) == (None, None)
    assert queries_c._rating_display(5.0, None) == (None, None)
    assert queries_c._rating_display(None, 500) == (None, None)
    # Exactly at the floor shows.
    assert queries_c._rating_display(4.8, queries_c.MIN_RATING_REVIEWS) == (
        "4.8",
        queries_c.MIN_RATING_REVIEWS,
    )


# ---------------------------------------------------------------------------
# eat_row() function contract
# ---------------------------------------------------------------------------


def test_eat_row_db_none_returns_empty() -> None:
    """``db=None`` short-circuits to ``[]`` -- callers who want the
    empty-state bridge can pass None for free."""
    assert queries_c.eat_row(None, now=_NOW_EVENING) == []


def test_eat_row_filters_to_open_now() -> None:
    """Providers whose ``_hours_status`` returns ``closed`` or ``unknown``
    are excluded; only ``open`` and ``closing-soon`` survive."""
    open_p = SimpleNamespace(
        slug="open-bar",
        provider_name="Open Bar",
        district="Downtown",
        google_rating=4.6,
    )
    closing_p = SimpleNamespace(
        slug="last-call",
        provider_name="Last Call",
        district="English Village",
        google_rating=4.4,
    )
    closed_p = SimpleNamespace(
        slug="closed-cafe",
        provider_name="Closed Cafe",
        district="North End",
        google_rating=4.9,
    )
    unknown_p = SimpleNamespace(
        slug="hours-tbd",
        provider_name="Hours TBD",
        district="Lakeshore",
        google_rating=4.7,
    )

    status_map = {
        "open-bar": ("open", "Open until 10"),
        "last-call": ("closing-soon", "Closes 9"),
        "closed-cafe": ("closed", "Closed now"),
        "hours-tbd": ("unknown", "Hours on profile"),
    }

    fake_db = _stub_db_returning([open_p, closing_p, closed_p, unknown_p])

    def fake_status(provider, *, now):  # noqa: ARG001
        return status_map[provider.slug]

    with patch.object(queries_c, "_hours_status", side_effect=fake_status):
        cards = queries_c.eat_row(fake_db, now=_NOW_EVENING)

    assert [c["slug"] for c in cards] == ["open-bar", "last-call"]
    assert cards[0]["status"] == "open"
    assert cards[1]["status"] == "closing-soon"


def test_eat_row_respects_limit() -> None:
    """``limit`` caps the returned list. Stops the for-loop early once
    the limit is reached so we don't pay for hours_status on extras."""
    providers = [
        SimpleNamespace(
            slug=f"p{i}",
            provider_name=f"Place {i}",
            district=None,
            google_rating=4.0 + (i * 0.05),
        )
        for i in range(8)
    ]
    fake_db = _stub_db_returning(providers)

    def all_open(provider, *, now):  # noqa: ARG001
        return ("open", "Open now")

    with patch.object(queries_c, "_hours_status", side_effect=all_open) as hours_status_mock:
        cards = queries_c.eat_row(fake_db, now=_NOW_EVENING, limit=3)

    assert len(cards) == 3
    # Contract-lock the early-stop: the loop must break as soon as
    # ``limit`` cards are collected, not slice at the end. With 8
    # all-open providers and ``limit=3``, ``_hours_status`` should be
    # called exactly 3 times -- never 4-8. Guards against a regression
    # where the function gathers all providers then truncates.
    assert hours_status_mock.call_count == 3


@pytest.mark.parametrize("bad_limit", [0, -1, -12])
def test_eat_row_non_positive_limit_returns_empty(bad_limit: int) -> None:
    """``limit <= 0`` short-circuits to ``[]``. The DB is never queried
    and ``_hours_status`` is never called -- the contract for a non-
    positive cap is "no cards" rather than "max(limit, 1) cards".

    Uses an exploding DB stub (rather than ``_stub_db_returning``) so a
    regression that drops the short-circuit and falls through to the DB
    query fails LOUDLY with a clear AssertionError, rather than silently
    appearing to "work" because the stub still returns rows."""

    class _ExplodingDB:
        def query(self, *args, **kwargs):  # noqa: ARG002
            raise AssertionError(
                "eat_row must short-circuit before calling db.query() when limit <= 0"
            )

    fake_db = _ExplodingDB()

    with patch.object(queries_c, "_hours_status") as hours_status_mock:
        cards = queries_c.eat_row(fake_db, now=_NOW_EVENING, limit=bad_limit)

    assert cards == []
    assert hours_status_mock.call_count == 0


def test_eat_row_skips_provider_when_hours_status_raises() -> None:
    """A malformed hours_structured row triggers an exception inside
    ``_hours_status``; the eat row must skip that provider and continue
    rather than 500 the home."""
    good = SimpleNamespace(slug="good", provider_name="Good", district=None, google_rating=4.5)
    bad = SimpleNamespace(slug="bad", provider_name="Bad", district=None, google_rating=4.8)

    def maybe_raise(provider, *, now):  # noqa: ARG001
        if provider.slug == "bad":
            raise ValueError("malformed hours row")
        return ("open", "Open now")

    fake_db = _stub_db_returning([bad, good])
    with patch.object(queries_c, "_hours_status", side_effect=maybe_raise):
        cards = queries_c.eat_row(fake_db, now=_NOW_EVENING)
    assert [c["slug"] for c in cards] == ["good"]


def test_eat_row_db_exception_returns_empty() -> None:
    """If the DB query itself throws (outage, schema drift), the row is
    empty and the template falls back to the bridge -- no 500."""

    class ExplodingSession:
        def query(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("db unavailable")

    assert queries_c.eat_row(ExplodingSession(), now=_NOW_EVENING) == []


def test_eat_row_pairs_curated_photo_by_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Provider whose slug is in the curated photo map gets that URL;
    a slug NOT in the map gets ``image_url=None`` and the partial draws
    a gradient."""
    monkeypatch.setattr(
        queries_c,
        "_load_eat_photos",
        lambda: {"mudshark-brewing": "https://images.unsplash.com/photo-x?w=600"},
    )
    in_map = SimpleNamespace(
        slug="mudshark-brewing",
        provider_name="Mudshark",
        district=None,
        google_rating=4.5,
    )
    not_in_map = SimpleNamespace(
        slug="some-other-place",
        provider_name="Some Other Place",
        district=None,
        google_rating=4.3,
    )
    fake_db = _stub_db_returning([in_map, not_in_map])

    with patch.object(
        queries_c,
        "_hours_status",
        side_effect=lambda p, *, now: ("open", "Open"),  # noqa: ARG005
    ):
        cards = queries_c.eat_row(fake_db, now=_NOW_EVENING)

    by_slug = {c["slug"]: c for c in cards}
    assert by_slug["mudshark-brewing"]["image_url"].startswith("https://")
    assert by_slug["some-other-place"]["image_url"] is None


def test_eat_row_no_zero_rating_or_count_in_output() -> None:
    """No card should expose a literal 0 / 0.0 to the template."""
    p = SimpleNamespace(slug="p", provider_name="P", district=None, google_rating=0.0)
    fake_db = _stub_db_returning([p])
    with patch.object(
        queries_c,
        "_hours_status",
        side_effect=lambda x, *, now: ("open", "Open"),  # noqa: ARG005
    ):
        cards = queries_c.eat_row(fake_db, now=_NOW_EVENING)
    assert cards[0]["rating"] is None  # zero-rating hidden, not "0.0"


# ---------------------------------------------------------------------------
# End-to-end /home rendering
# ---------------------------------------------------------------------------


def test_home_renders_without_legacy_eat_row_or_zero_counts() -> None:
    """The Sandstone home dropped the Lake Light eat-row (not in the prototype).

    The ``queries_c.eat_row`` contract is still unit-tested above; here we only
    guard that the home no longer ships the legacy eat-row markup and never
    fabricates a "0 listed" count (anti-confabulation).
    """
    import re

    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    body = r.text
    assert 'id="rd-body"' in body  # the v4 base layout
    assert "c-scroll-row" not in body
    assert "c-pc-name" not in body
    assert 'href="#"' not in body
    body_without_svg = re.sub(r"<svg[\s\S]*?</svg>", "", body)
    assert "0 listed" not in body_without_svg


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _StubQuery:
    """Just enough of a SQLAlchemy Query to back the eat_row path."""

    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *args, **kwargs):  # noqa: ARG002
        return self

    def order_by(self, *args, **kwargs):  # noqa: ARG002
        return self

    def limit(self, n):  # noqa: ARG002
        return self

    def all(self):
        return self._rows


def _stub_db_returning(rows):
    class _DB:
        def query(self, *args, **kwargs):  # noqa: ARG002
            return _StubQuery(rows)

    return _DB()


# Suppress "unused" warning on time import (test_helpers only).
_ = time
