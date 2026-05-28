"""Tests for ``app.chat.tier2_business_shortcut`` (Slice D).

The shortcut owns Tier 2's zero-token fast path for business-listing queries:
regex predicate match → category extraction → deterministic listing render.
The integration test exercises the wiring through ``tier2_handler``.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.chat import tier2_business_shortcut as shortcut
from app.chat import tier2_handler
from app.db.database import SessionLocal
from app.db.models import Provider

# ---------------------------------------------------------------------------
# try_business_listing_shortcut
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected_category",
    [
        ("find me a barber", "barber"),
        ("find a coffee shop in LHC", "coffee shop"),
        ("Find me a barber in Lake Havasu City", "barber"),
        ("show me coffee shops", "coffee shops"),
        ("show me a coffee shop near me", "coffee shop"),
        ("any good barbers", "barbers"),
        ("any barbers near me", "barbers"),
        ("any coffee shops in Lake Havasu", "coffee shops"),
        ("where can I find a barber", "barber"),
        ("where can I get a haircut?", "haircut"),
        ("list of coffee shops", "coffee shops"),
        ("list coffee shops in LHC", "coffee shops"),
        ("are there any good barbers", "barbers"),
        ("where's a barber", "barber"),
        # Slice F5: widened predicates. "good"/"best" tokens are absorbed into the
        # predicate so the extracted category is the raw category noun (cleaner SQL match).
        ("what are some coffee shops", "coffee shops"),
        ("what are the good barbers", "barbers"),
        ("what are some good barbers in LHC", "barbers"),
        ("got any taco places", "taco places"),
        ("got a good plumber", "plumber"),
        ("recommend a coffee shop", "coffee shop"),
        ("recommend any good barbers", "barbers"),
        ("recommend me a haircut place near me", "haircut place"),
        # Slice F5 fix: "an" article ahead of vowel-starting category must not get
        # truncated to "n X" by leftmost-match on the bare "a".
        ("find an electrician", "electrician"),
        ("find me an electrician in LHC", "electrician"),
        ("show me an italian restaurant", "italian restaurant"),
    ],
)
def test_shortcut_extracts_category(query: str, expected_category: str) -> None:
    filters = shortcut.try_business_listing_shortcut(query)
    assert filters is not None, f"shortcut should match {query!r}"
    assert filters.category == expected_category.lower()
    assert filters.parser_confidence >= 0.7
    assert filters.fallback_to_tier3 is False


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        # Plain factual lookups (Tier 1 territory).
        "phone number for the foundry",
        "is altitude open right now",
        "address for sloane's",
        # Event-shaped — must defer to LLM parser, which understands time windows.
        "find me a concert this weekend",
        "any events tonight",
        "any leagues for kids",
        "show me classes happening this week",
        "find a yoga class on Saturday",
        # Open-ended synthesis questions (Tier 3 territory).
        "what should I do tonight",
        "tell me about lake havasu activities",
        "we are visiting for two days, ideas?",
        # Long free-form questions — too complex for the shortcut.
        "find me the best place for kids on a hot summer day",
    ],
)
def test_shortcut_returns_none_for_non_listing_shapes(query: str) -> None:
    assert shortcut.try_business_listing_shortcut(query) is None


# ---------------------------------------------------------------------------
# Phase 7.6 — OPEN_NOW + category listing shortcut (q03 fix)
# ---------------------------------------------------------------------------


def test_open_now_listing_shortcut_matches_q03() -> None:
    """q03 shape must match the deterministic shortcut (pre-fix: FAIL — returns None)."""
    filters = shortcut.try_business_listing_shortcut("what restaurants are open now")
    assert filters is not None
    assert filters.category == "restaurant"
    assert filters.open_now is True
    assert filters.parser_confidence >= 0.7
    assert filters.fallback_to_tier3 is False


def test_open_now_listing_shortcut_returns_filters_with_open_now_true() -> None:
    """Sibling shapes: optional 'are', 'right now', other allow-listed nouns."""
    cases = [
        ("what cafes are open now", "cafe", True),
        ("what pharmacies are open right now", "pharmacy", True),
        ("what vets are open now", "veterinarian", True),
        ("what coffee shops are open now", "coffee shop", True),
        ("what gyms are open now", "gym", True),
    ]
    for query, expected_cat, expected_open in cases:
        filters = shortcut.try_business_listing_shortcut(query)
        assert filters is not None, query
        assert filters.category == expected_cat, query
        assert filters.open_now is expected_open, query


def test_open_now_listing_skips_when_event_shape_present() -> None:
    """Temporal/event tokens defer to the LLM parser — 'tonight' is in _EVENT_SHAPE_TOKENS."""
    assert shortcut.try_business_listing_shortcut("what restaurants are open tonight") is None
    assert shortcut.try_business_listing_shortcut("what bars are open this weekend") is None


@pytest.mark.parametrize(
    "query",
    [
        "what restaurants are open later",  # no now/right now
        "what restaurants open",  # missing temporal anchor (listing-prefix may match)
        "which restaurants are open now",  # wrong lead word (not 'what')
        "what is open now",  # no category noun
        "find me a restaurant open now",  # listing-prefix shape, not open-now listing
    ],
)
def test_open_now_listing_shortcut_negative_shapes(query: str) -> None:
    """OPEN_NOW branch must not fire — listing-prefix may still match with open_now=False."""
    filters = shortcut.try_business_listing_shortcut(query)
    assert filters is None or filters.open_now is not True, query


def test_shortcut_strips_locality_suffix() -> None:
    """'in LHC' / 'in Lake Havasu City' / 'near me' must not pollute the category."""
    for tail in (
        "in LHC",
        "in lhc",
        "in Lake Havasu",
        "in Lake Havasu City",
        "near me",
        "around here",
        "in town",
    ):
        filters = shortcut.try_business_listing_shortcut(f"find me a barber {tail}")
        assert filters is not None
        assert filters.category == "barber", f"tail {tail!r} polluted category: {filters.category!r}"


@pytest.mark.parametrize(
    "query,expected_category",
    [
        # §4.1 typo tolerance — common service-trade misspellings should
        # normalize to the canonical category before SQL hits.
        ("i need a plumer", "plumber"),
        ("i need a plummer in lhc", "plumber"),
        ("find me a barbar", "barber"),
        ("find a barbor near me", "barber"),
        ("find me an elektrician", "electrician"),
        ("i'm looking for an electrision", "electrician"),
        ("i need a mecanic", "mechanic"),
        ("find a vetrinarian", "veterinarian"),
        ("any good resturant", "restaurant"),
        ("show me a coffe shop", "coffee shop"),
        ("recommend a cofee shop", "coffee shop"),
        ("find a pharamcy near me", "pharmacy"),
        ("i need a carpentar", "carpenter"),
        ("find me a gymn", "gym"),
    ],
)
def test_shortcut_normalizes_common_typos(query: str, expected_category: str) -> None:
    filters = shortcut.try_business_listing_shortcut(query)
    assert filters is not None, f"shortcut should match {query!r}"
    assert filters.category == expected_category.lower(), (
        f"typo in {query!r} should normalize to {expected_category!r}, "
        f"got {filters.category!r}"
    )


def test_normalize_category_typos_preserves_unknown_tokens() -> None:
    """Tokens not in the alias map pass through untouched (lowercased downstream)."""
    assert shortcut._normalize_category_typos("plumer") == "plumber"
    assert shortcut._normalize_category_typos("italian restaurant") == "italian restaurant"
    assert shortcut._normalize_category_typos("italian resturant") == "italian restaurant"
    # Empty / blank input is a no-op.
    assert shortcut._normalize_category_typos("") == ""
    assert shortcut._normalize_category_typos("   ") == "   "


def test_saloon_not_remapped_to_salon() -> None:
    """In Lake Havasu, 'saloon' reads as a bar/tavern variant, not a misspelling
    of 'salon'. Guard against an over-eager alias regression."""
    assert shortcut._normalize_category_typos("saloon") == "saloon"


def test_shortcut_caps_category_word_count() -> None:
    """Three words is the practical ceiling for category lookups; longer phrasing is
    too likely to be a free-form question that should reach Tier 3 synthesis."""
    # 4 content words after the predicate -> should not match.
    assert shortcut.try_business_listing_shortcut("find me a really nice cozy bookshop") is None


# ---------------------------------------------------------------------------
# render_business_listing
# ---------------------------------------------------------------------------


def test_render_listing_with_provider_rows() -> None:
    rows = [
        {
            "type": "provider",
            "name": "Acme Cuts",
            "address": "100 Main St",
            "phone": "928-555-0101",
        },
        {
            "type": "provider",
            "name": "Bob's Barber Shop",
            "address": "200 McCulloch Blvd",
            "phone": "928-555-0202",
        },
    ]
    out = shortcut.render_business_listing(rows, "barbers")
    assert out is not None
    assert "barbers" in out.lower()
    assert "Acme Cuts" in out
    assert "Bob's Barber Shop" in out
    assert "100 Main St" in out
    assert "928-555-0101" in out


def test_render_listing_returns_none_when_no_provider_rows() -> None:
    """Mixed event/program responses without providers fall back to the LLM formatter."""
    rows = [{"type": "event", "name": "Some Event"}]
    assert shortcut.render_business_listing(rows, "anything") is None
    assert shortcut.render_business_listing([], "barbers") is None


def test_render_listing_caps_at_five() -> None:
    rows = [
        {"type": "provider", "name": f"Shop {i}", "address": "x", "phone": "y"}
        for i in range(20)
    ]
    out = shortcut.render_business_listing(rows, "shops")
    assert out is not None
    bullet_lines = [ln for ln in out.split("\n") if ln.startswith("•")]
    assert len(bullet_lines) == 5


def test_render_listing_handles_missing_address_or_phone() -> None:
    rows = [{"type": "provider", "name": "JustAName"}]
    out = shortcut.render_business_listing(rows, "places")
    assert out is not None
    assert "JustAName" in out


# ---------------------------------------------------------------------------
# Integration: tier2_handler wiring (Slice D end-to-end)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _insert_test_providers(db: Session, providers: list[dict]) -> list[str]:
    """Insert Google-style providers and return their ids for tearDown."""
    ids: list[str] = []
    for spec in providers:
        p = Provider(
            provider_name=spec["name"],
            category=spec.get("category", "beauty_personal_care"),
            address=spec.get("address"),
            phone=spec.get("phone"),
            source="google_places",
            google_place_id=f"test_{spec['name'].lower().replace(chr(32), '_')}",
            google_primary_category=spec.get("google_primary_category"),
            google_categories=spec.get("google_categories"),
            is_active=True,
            draft=False,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        ids.append(p.id)
    return ids


def test_handler_uses_shortcut_zero_tokens(db_session: Session) -> None:
    """Listing query → shortcut path → zero tokens, listing rendered deterministically."""
    ids = _insert_test_providers(
        db_session,
        [
            {
                "name": "Tier2Shortcut Acme Barber",
                "address": "100 Main St",
                "phone": "928-555-0101",
                "category": "beauty_personal_care",
                "google_primary_category": "barber_shop",
                "google_categories": ["barber_shop", "hair_care"],
            },
            {
                "name": "Tier2Shortcut Bobs Barber",
                "address": "200 McCulloch",
                "phone": "928-555-0202",
                "category": "beauty_personal_care",
                "google_primary_category": "barber_shop",
                "google_categories": ["barber_shop"],
            },
        ],
    )
    try:
        component_meta: dict = {}
        text, used, in_t, out_t = tier2_handler.try_tier2_with_usage(
            "find me a barber in LHC", component_meta=component_meta
        )
        assert text is not None, "shortcut should answer"
        assert used == 0, f"expected zero tokens, got {used}"
        assert in_t == 0
        assert out_t == 0
        assert "barber" in text.lower()
        assert component_meta.get("type") == "business_list"
        names = [it["name"] for it in component_meta["data"]["items"]]
        assert any("Tier2Shortcut" in n for n in names)
    finally:
        for pid in ids:
            row = db_session.get(Provider, pid)
            if row is not None:
                db_session.delete(row)
        db_session.commit()


def test_handler_open_now_listing_shortcut_zero_tokens(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """q03 end-to-end: shortcut → query(open_now=True) → deterministic render, zero tokens."""
    from datetime import datetime

    from app.chat import tier2_db_query
    from app.contrib.hours_helper import LAKE_HAVASU_TZ

    monkeypatch.setattr(
        tier2_db_query,
        "_now_lake_havasu",
        lambda: datetime(2026, 6, 15, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ),
    )
    ids = _insert_test_providers(
        db_session,
        [
            {
                "name": "Tier2OpenNow Miguel's",
                "category": "food_drink",
                "google_primary_category": "restaurant",
                "google_categories": ["restaurant", "food"],
            },
            {
                "name": "Tier2OpenNow Closed Diner",
                "category": "food_drink",
                "google_primary_category": "restaurant",
                "google_categories": ["restaurant"],
            },
        ],
    )
    try:
        for pid in ids:
            row = db_session.get(Provider, pid)
            if row and "OpenNow Miguel" in (row.provider_name or ""):
                row.hours_structured = {"monday": [{"open": "09:00", "close": "23:00"}]}
            elif row and "Closed Diner" in (row.provider_name or ""):
                row.hours_structured = {"monday": [{"open": "18:00", "close": "19:00"}]}
        db_session.commit()

        component_meta: dict = {}
        text, used, in_t, out_t = tier2_handler.try_tier2_with_usage(
            "what restaurants are open now", component_meta=component_meta
        )
        assert text is not None, "shortcut+open_now should produce a listing"
        assert used == 0, f"expected zero tokens (no Haiku), got {used}"
        assert in_t == 0
        assert out_t == 0
        assert component_meta.get("type") == "business_list"
        names = [it["name"] for it in component_meta["data"]["items"]]
        assert any("Tier2OpenNow Miguel" in n for n in names)
        assert not any("Closed Diner" in n for n in names)
    finally:
        for pid in ids:
            row = db_session.get(Provider, pid)
            if row is not None:
                db_session.delete(row)
        db_session.commit()


def test_handler_falls_through_when_shortcut_finds_no_providers(db_session: Session) -> None:
    """If the shortcut shape matches but no providers come back, fall through to the
    LLM parser path so the user still gets an answer (rather than a misleading empty
    listing). For this test we don't have an Anthropic key in CI, so we just assert
    that the shortcut didn't claim a zero-token answer."""
    # Search for a category that no test provider matches.
    text, used, in_t, out_t = tier2_handler.try_tier2_with_usage(
        "find me a totally-nonexistent-category-zzz in LHC"
    )
    # Either Tier 2 LLM parser fell through (returning None) or returned something
    # non-zero tokens. The fast path must NOT have claimed a zero-token answer.
    if text is not None:
        assert used != 0 or used is None, "shortcut should not claim zero tokens here"


def test_handler_skips_shortcut_for_tier1_shaped_queries(db_session: Session) -> None:
    """Factual Tier 1 lookups must not hit the Tier 2 shortcut — they belong on the
    Tier 1 deterministic path. Confirm the shortcut returns None for these shapes."""
    for q in ("phone number for the foundry", "is altitude open right now"):
        assert shortcut.try_business_listing_shortcut(q) is None


def test_handler_handles_plural_query_against_singular_google_tag(db_session: Session) -> None:
    """Slice D fix: 'any good coffee shops' (plural) must still match providers
    tagged 'coffee_shop' (Google's singular underscore form). Regression caught
    by the query battery on first run."""
    ids = _insert_test_providers(
        db_session,
        [
            {
                "name": "Tier2Singular Bean Cafe",
                "address": "300 Channel Dr",
                "phone": "928-555-0303",
                "category": "food_drink",
                "google_primary_category": "cafe",
                "google_categories": ["cafe", "coffee_shop", "food", "store"],
            },
            {
                "name": "Tier2Singular Cool Beans Coffee",
                "address": "400 McCulloch Blvd",
                "phone": "928-555-0404",
                "category": "food_drink",
                "google_primary_category": "coffee_shop",
                "google_categories": ["coffee_shop", "food"],
            },
        ],
    )
    try:
        component_meta: dict = {}
        text, used, in_t, out_t = tier2_handler.try_tier2_with_usage(
            "any good coffee shops", component_meta=component_meta
        )
        assert text is not None, "shortcut should answer plural-form query"
        assert used == 0, f"expected zero tokens, got {used}"
        assert in_t == 0
        assert out_t == 0
        # Header should pluralize naturally.
        assert "coffee shops" in text.lower()
        assert component_meta.get("type") == "business_list"
        names = [it["name"] for it in component_meta["data"]["items"]]
        assert any("Tier2Singular" in n for n in names)
    finally:
        for pid in ids:
            row = db_session.get(Provider, pid)
            if row is not None:
                db_session.delete(row)
        db_session.commit()


def test_pluralize_for_header_singular_to_plural() -> None:
    assert shortcut._pluralize_for_header("barber") == "barbers"
    assert shortcut._pluralize_for_header("coffee shop") == "coffee shops"
    assert shortcut._pluralize_for_header("haircut") == "haircuts"


def test_pluralize_for_header_already_plural_unchanged() -> None:
    assert shortcut._pluralize_for_header("barbers") == "barbers"
    assert shortcut._pluralize_for_header("coffee shops") == "coffee shops"


def test_pluralize_for_header_y_to_ies() -> None:
    assert shortcut._pluralize_for_header("bakery") == "bakeries"
    # vowel-y stays additive.
    assert shortcut._pluralize_for_header("attorney") == "attorneys"


def test_pluralize_for_header_sh_ch_x() -> None:
    assert shortcut._pluralize_for_header("church") == "churches"
    assert shortcut._pluralize_for_header("car wash") == "car washes"
