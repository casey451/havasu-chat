"""Unit tests for the cross-source dedup audit scoring core (no DB).

Run from the owner's terminal: pytest tests/test_cross_source_dedup_audit.py -q
"""

from __future__ import annotations

from datetime import datetime

from scripts.cross_source_dedup_audit import (
    ProvRow,
    _norm_domain,
    _norm_phone,
    _order_keep_dup,
    find_provider_pairs,
)


def _row(rid, name, **kw):
    base = dict(
        source=None,
        website=None,
        phone=None,
        lat=None,
        lng=None,
        google_place_id=None,
        verified=False,
        created_at=None,
    )
    base.update(kw)
    return ProvRow(id=rid, name=name, **base)


def test_norm_domain_strips_scheme_www_path():
    assert _norm_domain("https://www.JoesBar.com/contact?x=1") == "joesbar.com"
    assert _norm_domain("http://joesbar.com") == "joesbar.com"
    assert _norm_domain("joesbar.com:8080/") == "joesbar.com"
    assert _norm_domain("") is None
    assert _norm_domain(None) is None


def test_norm_phone_last10_strips_country_code():
    assert _norm_phone("(702) 787-9568") == "7027879568"
    assert _norm_phone("+1 702-787-9568") == "7027879568"
    assert _norm_phone("12345") is None
    assert _norm_phone(None) is None


def _pairs(rows, **kw):
    pairs, _shared = find_provider_pairs(rows, **kw)
    return pairs


def test_google_place_id_is_definite_auto():
    rows = [
        _row("a", "Joe's Bar", google_place_id="GP1", source="google_places"),
        _row("b", "Totally Different Name", google_place_id="GP1", source="osm"),
    ]
    pairs = _pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].reason == "google_place_id"
    assert pairs[0].action == "auto_merge_eligible"
    assert pairs[0].score == 100.0


def test_website_domain_match_auto():
    # website match is now ALWAYS needs_review (soft signal): a shared domain
    # alone -- even with an identical name -- goes to a human, never auto.
    rows = [
        _row("a", "Joe's Grill", website="https://www.joes.com", source="google_places"),
        _row("b", "Joes Grill", website="http://joes.com/menu", source="go_lake_havasu"),
    ]
    pairs = _pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].reason == "website"
    assert pairs[0].action == "needs_review"


def test_website_colocated_distinct_venues_are_needs_review():
    # The resort case: same domain, 0m apart, DIFFERENT venues -> needs_review,
    # NOT auto. (Geo must not promote these -- co-location is the trap.)
    rows = [
        _row(
            "a",
            "WET Pool Bar",
            website="http://nautical.com",
            lat=34.48,
            lng=-114.32,
            source="go_lake_havasu",
        ),
        _row(
            "b",
            "Turtle Grille",
            website="http://nautical.com/dine",
            lat=34.48,
            lng=-114.32,
            source="go_lake_havasu",
        ),
    ]
    pairs = _pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].reason == "website"
    assert pairs[0].action == "needs_review"


def test_phone_match_is_needs_review():
    # phone is a soft signal too (only google_place_id auto-merges).
    rows = [
        _row("a", "Joe's", phone="(702) 787-9568", source="osm"),
        _row("b", "Joe", phone="+1 7027879568", source="npi_registry"),
    ]
    pairs = _pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].reason == "phone"
    assert pairs[0].action == "needs_review"


def test_geo_plus_fuzzy_name_is_review():
    # Minor punctuation/spelling divergence at the same spot -- the real prod
    # geo+name hits scored ~100 (identical names); this clears 88 without being
    # slug-identical, exercising the fuzzy tier rather than an exact match.
    rows = [
        _row("a", "Joe's Bar and Grill", lat=34.4839, lng=-114.3225, source="osm"),
        _row("b", "Joes Bar and Grill", lat=34.48391, lng=-114.32251, source="go_lake_havasu"),
    ]
    pairs = _pairs(rows, fuzzy_threshold=88.0)
    assert len(pairs) == 1
    assert pairs[0].reason == "geo+name"
    assert pairs[0].action == "needs_review"
    assert pairs[0].distance_m is not None and pairs[0].distance_m <= 50


def test_geo_plus_diverging_name_below_threshold_not_paired():
    # The fixture that wrongly failed before: "&" vs "and" + apostrophe pushes
    # token_sort_ratio under 88, so this pair must NOT be flagged.
    rows = [
        _row("a", "Joe's Bar & Grill", lat=34.4839, lng=-114.3225, source="osm"),
        _row("b", "Joes Bar and Grill", lat=34.48391, lng=-114.32251, source="go_lake_havasu"),
    ]
    assert _pairs(rows, fuzzy_threshold=88.0) == []


def test_far_apart_same_name_not_paired():
    rows = [
        _row("a", "Java Cafe", lat=34.48, lng=-114.32),
        _row("b", "Java Cafe", lat=34.60, lng=-114.10),
    ]
    assert _pairs(rows) == []


def test_identity_beats_geo_name_for_same_pair():
    # Same pair qualifies on both website (99) and geo+name; website wins.
    rows = [
        _row("a", "Joe's", website="joes.com", lat=34.48, lng=-114.32, source="google_places"),
        _row("b", "Joes", website="www.joes.com", lat=34.48001, lng=-114.32001, source="osm"),
    ]
    pairs = _pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].reason == "website"


def test_website_beats_geo_name_at_perfect_name_ratio():
    # Identical names at the same spot score geo+name=100, but website tier
    # must still win (tier precedence, not raw score).
    rows = [
        _row(
            "a",
            "Joe's Bar",
            website="https://joes.com",
            lat=34.48,
            lng=-114.32,
            source="google_places",
        ),
        _row(
            "b",
            "Joe's Bar",
            website="http://www.joes.com",
            lat=34.48,
            lng=-114.32,
            source="osm",
        ),
    ]
    pairs = _pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].reason == "website"
    assert pairs[0].score == 99.0


def test_shared_phone_above_cap_is_flagged_not_paired():
    # A switchboard number on 6 rows must NOT mint C(6,2)=15 auto-merge pairs.
    rows = [_row(str(i), f"Tenant {i}", phone="(928) 855-0000") for i in range(6)]
    pairs, shared = find_provider_pairs(rows, max_group_size=4)
    assert pairs == []
    assert len(shared) == 1
    assert shared[0].reason == "phone"
    assert shared[0].count == 6
    assert len(shared[0].sample_names) == 5  # capped sample


def test_group_at_cap_still_pairs():
    rows = [_row(str(i), f"Loc {i}", website="shared.com") for i in range(4)]
    pairs, shared = find_provider_pairs(rows, max_group_size=4)
    assert shared == []
    assert len(pairs) == 6  # C(4,2), all website-reason
    assert all(p.reason == "website" for p in pairs)


def test_keep_dup_uses_source_priority():
    # google_places (1) outranks go_lake_havasu (3) -> google row is keeper.
    g = _row("g", "Joe's", google_place_id="GP1", source="google_places")
    c = _row("c", "Joe's", google_place_id="GP1", source="go_lake_havasu")
    keep, dup = _order_keep_dup(c, g)
    assert keep.id == "g"
    assert dup.id == "c"


def test_keep_dup_tiebreak_created_at():
    older = _row("o", "X", source="osm", created_at=datetime(2024, 1, 1))
    newer = _row("n", "X", source="osm", created_at=datetime(2025, 1, 1))
    keep, dup = _order_keep_dup(newer, older)
    assert keep.id == "o"


def test_three_way_website_group_yields_three_pairs():
    rows = [
        _row("a", "A", website="joes.com"),
        _row("b", "B", website="www.joes.com"),
        _row("c", "C", website="https://joes.com/x"),
    ]
    pairs = _pairs(rows)
    assert len(pairs) == 3
    assert all(p.reason == "website" for p in pairs)


def test_dispersed_website_group_is_flagged_not_paired():
    # The "Simply Savage Designs" prod case: one designer/aggregator domain
    # credited as the website of distinct shops 1-6 km apart. A small group (<=
    # cap) but geographically dispersed -> a "dispersed" shared-key flag, no pairs.
    rows = [
        _row("a", "Action Sports", website="simplysavage.com", lat=34.48, lng=-114.32),
        _row("b", "Golden Hour Salon", website="simplysavage.com", lat=34.49, lng=-114.35),
        _row("c", "Project 72 Baits", website="simplysavage.com", lat=34.52, lng=-114.30),
    ]
    pairs, shared = find_provider_pairs(rows)
    assert pairs == []
    assert len(shared) == 1
    assert shared[0].reason == "website"
    assert shared[0].cause == "dispersed"
    assert shared[0].count == 3
    assert shared[0].spread_m is not None and shared[0].spread_m > 500


def test_colocated_website_group_still_pairs():
    # The resort sub-venues: same domain, co-located (a few meters apart) -> NOT
    # dispersed, so they still pair as needs_review for a human to judge.
    rows = [
        _row("a", "WET Pool Bar", website="nautical.com", lat=34.48, lng=-114.32),
        _row("b", "Turtle Grille", website="nautical.com", lat=34.48001, lng=-114.32001),
        _row("c", "Naked Turtle", website="nautical.com", lat=34.47999, lng=-114.31999),
    ]
    pairs, shared = find_provider_pairs(rows)
    assert shared == []
    assert len(pairs) == 3
    assert all(p.reason == "website" and p.action == "needs_review" for p in pairs)


def test_dispersion_guard_ignored_when_coords_missing():
    # Without coords a soft-key group cannot be judged dispersed, so it keeps
    # pairing (the no-geo website path must be unchanged).
    rows = [
        _row("a", "A", website="shared.com"),
        _row("b", "B", website="shared.com"),
        _row("c", "C", website="shared.com"),
    ]
    pairs, shared = find_provider_pairs(rows)
    assert shared == []
    assert len(pairs) == 3


def test_dispersed_phone_group_within_cap_is_flagged():
    # A chain's central number on a small set of far-apart listings -> dispersed.
    rows = [
        _row("a", "Outlet East", phone="(928) 855-0000", lat=34.48, lng=-114.32),
        _row("b", "Outlet West", phone="(928) 855-0000", lat=34.50, lng=-114.40),
    ]
    pairs, shared = find_provider_pairs(rows)
    assert pairs == []
    assert len(shared) == 1
    assert shared[0].reason == "phone"
    assert shared[0].cause == "dispersed"


def test_gpid_not_demoted_by_spread():
    # google_place_id is a global identity: two rows sharing one are the same
    # place even with a bad coordinate far away. Must still auto-merge, never
    # flagged as dispersed.
    rows = [
        _row("a", "Joe's", google_place_id="GP1", lat=34.48, lng=-114.32, source="google_places"),
        _row("b", "Joe's", google_place_id="GP1", lat=34.90, lng=-114.90, source="osm"),
    ]
    pairs, shared = find_provider_pairs(rows)
    assert shared == []
    assert len(pairs) == 1
    assert pairs[0].reason == "google_place_id"
    assert pairs[0].action == "auto_merge_eligible"


def test_spread_threshold_is_tunable():
    # Members ~1.1 km apart: dispersed at the 500 m default, but a campus that
    # legitimately spans more can raise the bound to keep the group paired.
    rows = [
        _row("a", "A", website="campus.com", lat=34.48, lng=-114.32),
        _row("b", "B", website="campus.com", lat=34.49, lng=-114.32),
    ]
    flagged, shared = find_provider_pairs(rows)
    assert flagged == [] and len(shared) == 1
    paired, shared2 = find_provider_pairs(rows, max_shared_key_spread_m=5000.0)
    assert shared2 == [] and len(paired) == 1
