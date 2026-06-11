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
