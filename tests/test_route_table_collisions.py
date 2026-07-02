"""Route-table collision guard (audit 2026-07-01).

Router mount order is collision-safe today but ordering-sensitive by
construction: v1_master_spec_router mounts FIRST and silently wins any
(method, path) tie a later router introduces (C3's history endpoint hit this
on a red CI run). This test turns that from a code-review convention into a
CI failure with the offending pattern named.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi.routing import APIRoute

from app.main import app


def test_no_two_routes_share_method_and_path() -> None:
    seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            if method == "HEAD":
                continue
            seen[(method, route.path)].append(route.endpoint.__module__)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dupes, (
        "Duplicate (method, path) registrations — the FIRST mounted router "
        f"silently wins and the later one is dead: {dupes}"
    )


def test_route_table_is_nonempty_sanity() -> None:
    assert sum(1 for r in app.routes if isinstance(r, APIRoute)) > 100
