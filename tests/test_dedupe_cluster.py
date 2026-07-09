"""S1 — dedupe clustering engine (2026-07-06).

Covers all four match signals and the three relationship types, seeded with the
verified cluster shapes from the data-quality audit (Denny's slug-family, chain
multi-location, practice parent/child).
"""

from __future__ import annotations

from app.dedupe.cluster import (
    ProviderRecord,
    address_key,
    cluster_providers,
    name_key,
)


def _r(id, name, **kw) -> ProviderRecord:
    return ProviderRecord(id=id, name=name, **kw)


# --- normalization -----------------------------------------------------------


def test_address_key_strips_suite_and_folds() -> None:
    a = address_key("100 Main St, Ste 5, Lake Havasu City, AZ 86403")
    b = address_key("100 Main St #5, Lake Havasu City AZ")
    assert a == b == "100 main st"


def test_name_key_reuses_slugify() -> None:
    assert name_key("Denny's Restaurant") == "denny-s-restaurant"


# --- signal 1: google_place_id ----------------------------------------------


def test_same_place_id_clusters_even_with_different_names() -> None:
    recs = [
        _r("1", "Joe's Bar", google_place_id="PID1"),
        _r("2", "Joes Bar & Grill", google_place_id="PID1"),
        _r("3", "Unrelated Cafe", google_place_id="PID2"),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1
    assert {m.id for m in clusters[0].members} == {"1", "2"}


# --- signal 2: name + address ------------------------------------------------


def test_name_plus_address_clusters() -> None:
    recs = [
        _r("1", "Turtle Grille", address="123 Beach Dr, Lake Havasu City, AZ"),
        _r("2", "Turtle Grille", address="123 Beach Dr Ste B, Lake Havasu City AZ"),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1
    assert clusters[0].relationship_type == "duplicate"


# --- signal 3: name + phone --------------------------------------------------


def test_name_plus_phone_clusters() -> None:
    recs = [
        _r("1", "Shugrue's", phone="(928) 453-1400"),
        _r("2", "Shugrue's", phone="928-453-1400"),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1


# --- signal 4: slug-family ---------------------------------------------------


def test_trailing_int_slug_family_clusters_at_same_address() -> None:
    recs = [
        _r("1", "Great Clips", address="200 Swanson Ave"),
        _r("2", "Great Clips 2", address="200 Swanson Ave"),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1


def test_token_subset_name_clusters_at_same_address_and_phone() -> None:
    # Token-subset is a weak signal, so it requires the SAME phone to union.
    recs = [
        _r("1", "Denny's", address="1500 McCulloch Blvd", phone="(928) 855-4776"),
        _r("2", "Denny's Restaurant", address="1500 McCulloch Blvd", phone="928-855-4776"),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1


def test_token_subset_with_different_phones_does_not_cluster() -> None:
    # The umbrella-brokerage false merge: two distinct agents at one brokerage
    # address share the brand token but have different phones → NOT merged.
    recs = [
        _r("1", "Realty One Group", address="1971 McCulloch Blvd", phone="(928) 680-7350"),
        _r("2", "Noreen Gilmartin, Realty One Group", address="1971 McCulloch Blvd", phone="(928) 302-0269"),
    ]
    assert cluster_providers(recs) == []


def test_same_name_different_address_does_not_falsely_cluster() -> None:
    # No shared signal (different address, no phone/place_id) → NOT a cluster.
    recs = [
        _r("1", "Great Clips", address="200 Swanson Ave"),
        _r("2", "Great Clips", address="999 Other Rd"),
    ]
    assert cluster_providers(recs) == []


# --- relationship types ------------------------------------------------------


def test_multi_location_when_same_name_spans_addresses() -> None:
    # Two chain locations sharing a corporate phone → clustered, but KEPT as
    # siblings (multi_location), not retired.
    recs = [
        _r("1", "Circle K", address="100 A St", phone="(928) 555-0000"),
        _r("2", "Circle K", address="200 B St", phone="928.555.0000"),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1
    assert clusters[0].relationship_type == "multi_location"


def test_parent_child_when_longer_name_adds_a_provider() -> None:
    recs = [
        _r("1", "Southwest Primary Care", address="90 Care Way", phone="928-555-1000", review_count=100),
        _r("2", "Southwest Primary Care Dr Lonial", address="90 Care Way", phone="(928) 555-1000", review_count=0),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.primary.id == "1"  # the parent org (more reviews) is primary
    assert c.relationship_type == "parent_child"


def test_amenity_at_a_venue_is_parent_child_not_retired() -> None:
    # A high-value destination inside another venue must not be retired as a dup.
    recs = [
        _r("1", "London Bridge Beach", address="1340 McCulloch Blvd", phone="928-453-8686", review_count=3033),
        _r("2", "Lions Dog Park @ London Bridge Beach", address="1340 McCulloch Blvd", phone="928-453-8686", review_count=945),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1
    assert clusters[0].relationship_type == "parent_child"


def test_duplicate_is_the_default_relationship() -> None:
    recs = [
        _r("1", "Shugrue's", phone="928-453-1400"),
        _r("2", "Shugrue's", phone="(928) 453-1400"),
    ]
    assert cluster_providers(recs)[0].relationship_type == "duplicate"


# --- primary selection + clones ---------------------------------------------


def test_primary_prefers_place_id_then_reviews() -> None:
    recs = [
        _r("1", "PNC Bank", address="1 Bank St", review_count=5),
        _r("2", "PNC Bank", address="1 Bank St", google_place_id="PID", review_count=2),
        _r("3", "PNC Bank", address="1 Bank St", review_count=50),
    ]
    clusters = cluster_providers(recs)
    assert len(clusters) == 1
    assert clusters[0].primary.id == "2"  # has a google_place_id
    assert {c.id for c in clusters[0].clones} == {"1", "3"}


def test_singletons_are_not_returned() -> None:
    assert cluster_providers([_r("1", "Solo Shop", address="1 A St")]) == []
