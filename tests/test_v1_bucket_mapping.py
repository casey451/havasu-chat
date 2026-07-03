"""Regression: legacy-category -> master bucket mapping (P0 follow-up).

The legacy->bucket map used to key on spec-style slugs that never matched the
stored ``Provider.category`` values. ``bucket_for_legacy_category`` is still used
across the directory (app/categories/*, app/v1/serializers, app/v1/query_log),
so this pure-function regression stays. The ``/api/businesses`` endpoint tests
that used to live here were removed with the endpoint itself (2026-07-02 — no
consumers, no promised API).
"""

from __future__ import annotations

import pytest

from app.v1.categories import bucket_for_legacy_category


@pytest.mark.parametrize(
    "legacy,bucket",
    [
        ("lake_recreation", "recreation-outdoors"),
        ("boat_rental", "recreation-outdoors"),
        ("retail", "shopping"),
        ("lodging", "stay"),
        ("fitness_sports", "sports-fitness"),
        ("beauty_personal_care", "services"),
        ("professional_services", "services"),
        ("restaurant", "food-drink"),
        ("entertainment_attractions", "events"),
    ],
)
def test_bucket_for_legacy_category_uses_real_values(legacy: str, bucket: str) -> None:
    assert bucket_for_legacy_category(legacy) == bucket
