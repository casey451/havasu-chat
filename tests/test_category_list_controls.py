"""UX-2: server-side Open-now filter + sort + pagination for leaf/trade list
pages (app.categories.router._apply_list_controls). Pure function — no DB.

The Open-now filter keys on each card's ``is_open`` flag, which the upstream
card builder computes with ``is_open_now(p, now=now_lake_havasu())`` — i.e. the
America/Phoenix clock (no DST). That timezone derivation is covered by the
is_open_now tests; here we verify the filter/sort/paginate layer on top.
"""

from __future__ import annotations

from app.categories.router import _LEAF_PAGE_SIZE, _apply_list_controls

BASE = "/categories/eat-and-drink/restaurants"


def _cards(n: int, *, open_every: int = 0):
    out = []
    for i in range(n):
        is_open = (open_every and i % open_every == 0) or False
        out.append({"name": f"Biz {i:03d}", "is_open": True if is_open else False})
    return out


def test_default_is_top_sort_no_filter_first_page():
    cards = _cards(10)
    visible, ctrl = _apply_list_controls({}, cards, base_path=BASE)
    assert ctrl["sort"] == "top"
    assert ctrl["open_now"] is False
    assert ctrl["page"] == 1
    assert ctrl["total_pages"] == 1
    assert visible == cards  # order preserved (dampened-rating order from caller)


def test_open_now_filters_strictly_true():
    cards = _cards(9, open_every=3)  # indices 0,3,6 open
    # add a None-is_open card to prove strict True (not truthy) filtering
    cards.append({"name": "Unknown hours", "is_open": None})
    visible, ctrl = _apply_list_controls({"open": "1"}, cards, base_path=BASE)
    assert ctrl["open_now"] is True
    assert ctrl["shown_total"] == 3
    assert all(c["is_open"] is True for c in visible)


def test_az_sort_orders_by_name():
    cards = [{"name": "Zebra", "is_open": False}, {"name": "apple", "is_open": False},
             {"name": "Mango", "is_open": False}]
    visible, ctrl = _apply_list_controls({"sort": "az"}, cards, base_path=BASE)
    assert ctrl["sort"] == "az"
    assert [c["name"] for c in visible] == ["apple", "Mango", "Zebra"]


def test_favorites_sort_accepted_and_preserves_order():
    # P4: "Top rated" (?sort=favorites) keeps the dampened-rating order the cards
    # arrive in (the daily Featured shuffle is suppressed upstream) — no re-sort.
    cards = _cards(5)
    visible, ctrl = _apply_list_controls({"sort": "favorites"}, cards, base_path=BASE)
    assert ctrl["sort"] == "favorites"
    assert visible == cards


def test_featured_default_and_favorites_have_distinct_urls():
    _, ctrl = _apply_list_controls({}, _cards(3), base_path=BASE)
    # Featured (the daily-shuffle default) = the bare route; "Top rated" carries
    # ?sort=favorites — the bug was the "Top rated" chip pointing at the bare URL.
    assert ctrl["url_top"] == BASE
    assert ctrl["url_favorites"] == f"{BASE}?sort=favorites"


def test_favorites_preserves_rating_order_while_featured_demotes_closed():
    # Cards arrive in dampened-rating order: a top-rated-but-closed place first.
    cards = [
        {"name": "Top but closed", "is_open": False, "has_reviews": True},
        {"name": "Open lower", "is_open": True, "has_reviews": True},
    ]
    fav, _ = _apply_list_controls({"sort": "favorites"}, list(cards), base_path=BASE)
    assert [c["name"] for c in fav] == ["Top but closed", "Open lower"]  # preserved
    feat, _ = _apply_list_controls({}, list(cards), base_path=BASE)
    assert [c["name"] for c in feat] == ["Open lower", "Top but closed"]  # open lifted


def test_cuisine_facet_filters_cards_by_derived_token():
    # WS9a: cards carry a derived ``cuisine`` token; ?cuisine=mexican keeps only
    # those, and shown_total reflects the narrowed set.
    cards = [
        {"name": "Taqueria", "is_open": True, "cuisine": "mexican"},
        {"name": "Trattoria", "is_open": True, "cuisine": "italian"},
        {"name": "Cantina", "is_open": True, "cuisine": "mexican"},
        {"name": "Place card", "is_open": None, "cuisine": ""},
    ]
    visible, ctrl = _apply_list_controls({"cuisine": "mexican"}, cards, base_path=BASE)
    assert ctrl["cuisine"] == "mexican"
    assert ctrl["shown_total"] == 2
    assert [c["name"] for c in visible] == ["Taqueria", "Cantina"]


def test_cuisine_absent_is_noop_and_preserves_urls():
    # No cuisine param -> cuisine is None and the control URLs are byte-identical
    # to the pre-WS9a contract (no ?cuisine= leaks in).
    _, ctrl = _apply_list_controls({}, _cards(3), base_path=BASE)
    assert ctrl["cuisine"] is None
    assert ctrl["url_top"] == BASE
    assert ctrl["url_favorites"] == f"{BASE}?sort=favorites"
    assert ctrl["url_open_on"] == f"{BASE}?open=1"


def test_cuisine_preserved_across_sort_and_open_and_pager_urls():
    # Every sort/open/pager link keeps the active cuisine narrowing.
    cards = [{"name": f"M{i}", "is_open": True, "cuisine": "mexican"} for i in range(70)]
    _, ctrl = _apply_list_controls({"cuisine": "mexican"}, cards, base_path=BASE)
    assert ctrl["url_favorites"] == f"{BASE}?cuisine=mexican&sort=favorites"
    assert ctrl["url_open_on"] == f"{BASE}?cuisine=mexican&open=1"
    assert ctrl["url_next"] == f"{BASE}?cuisine=mexican&page=2"


def test_pagination_slices_and_links():
    cards = _cards(130)
    visible, ctrl = _apply_list_controls({"page": "2"}, cards, base_path=BASE)
    assert _LEAF_PAGE_SIZE == 60
    assert ctrl["total_pages"] == 3
    assert ctrl["page"] == 2
    assert len(visible) == 60
    assert visible[0]["name"] == "Biz 060"
    assert ctrl["has_prev"] is True and ctrl["has_next"] is True
    assert ctrl["url_next"] == f"{BASE}?page=3"
    assert ctrl["url_prev"] == BASE  # page 1 drops the param


def test_overflow_page_clamps_to_last():
    visible, ctrl = _apply_list_controls({"page": "99"}, _cards(70), base_path=BASE)
    assert ctrl["page"] == 2
    assert ctrl["has_next"] is False


def test_invalid_params_fall_back():
    _, ctrl = _apply_list_controls(
        {"sort": "bogus", "page": "abc"}, _cards(3), base_path=BASE
    )
    assert ctrl["sort"] == "top"
    assert ctrl["page"] == 1


def test_url_builders_combine_sort_and_open():
    _, ctrl = _apply_list_controls({"sort": "az", "open": "1"}, _cards(3), base_path=BASE)
    # Switching to Top keeps the open filter; A–Z chip keeps open; open-off clears it.
    assert ctrl["url_az"] == f"{BASE}?sort=az&open=1"
    assert ctrl["url_top"] == f"{BASE}?open=1"
    assert ctrl["url_open_off"] == f"{BASE}?sort=az"
    assert "open=1" in ctrl["url_open_on"]


def test_featured_sort_keeps_query_match_above_open_reviewed():
    # #666 regression: the ?q= relevance float marks matched cards
    # is_query_match; the Featured re-sort must keep them ahead of the
    # open/has_reviews demotion (a closed, not-yet-reviewed on-topic shop
    # used to sink under every generic open/reviewed row).
    cards = [
        {"name": "Generic Open Reviewed", "is_open": True, "has_reviews": True},
        {
            "name": "On-topic But Closed",
            "is_open": False,
            "has_reviews": False,
            "is_query_match": True,
        },
        {"name": "Another Generic", "is_open": True, "has_reviews": True},
    ]
    visible, _ = _apply_list_controls({}, cards, base_path=BASE)
    assert visible[0]["name"] == "On-topic But Closed"


def test_featured_sort_sponsored_still_outranks_query_match():
    cards = [
        {"name": "Match", "is_open": True, "has_reviews": True, "is_query_match": True},
        {"name": "Paid Pin", "is_open": False, "has_reviews": False, "is_sponsored": True},
    ]
    visible, _ = _apply_list_controls({}, cards, base_path=BASE)
    assert visible[0]["name"] == "Paid Pin"
