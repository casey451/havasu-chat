"""Tests for the outbound link-health checker (no real network, no real DB)."""

from __future__ import annotations

from app.monitoring import link_health as lh


# --- categorize ------------------------------------------------------------ #
def test_categorize_buckets() -> None:
    assert lh.categorize(200) == lh.OK
    assert lh.categorize(404) == lh.BROKEN
    assert lh.categorize(500) == lh.BROKEN
    assert lh.categorize(403) == lh.BLOCKED_BY_SITE
    assert lh.categorize(429) == lh.BLOCKED_BY_SITE
    assert lh.categorize(401) == lh.BLOCKED_BY_SITE


# --- collect_links (fake DB returns canned rows per execute() call) --------- #
class _FakeDB:
    def __init__(self, *result_sets):
        self._queue = list(result_sets)

    def execute(self, _stmt):
        return self._queue.pop(0)


def test_collect_links_maps_providers_and_events() -> None:
    providers = [
        ("p1", "Joe's Diner", "https://joes.example", "https://fb.com/joes"),
        ("p2", "No Web Co", "", None),
    ]
    events = [("e1", "Concert", "https://tix.example/show")]
    refs = lh.collect_links(_FakeDB(providers, events))
    kinds = sorted((r.kind, r.url) for r in refs)
    assert kinds == [
        ("event_url", "https://tix.example/show"),
        ("provider_facebook", "https://fb.com/joes"),
        ("provider_website", "https://joes.example"),
    ]


# --- scan_links: dedup, categories, actionable, limit, pause --------------- #
def _refs(*urls: str) -> list[lh.LinkRef]:
    return [lh.LinkRef(u, "provider_website", f"id{i}", f"label{i}") for i, u in enumerate(urls)]


def test_scan_dedups_identical_urls() -> None:
    refs = _refs("https://a.example", "https://a.example", "https://b.example")
    report = lh.scan_links(refs, checker=lambda u: (lh.OK, 200, "HTTP 200"), sleeper=lambda s: None)
    assert len(report.results) == 2
    assert report.skipped_duplicate_urls == 1


def test_scan_categories_and_actionable() -> None:
    table = {
        "https://ok.example": (lh.OK, 200, "HTTP 200"),
        "https://dead.example": (lh.BROKEN, 404, "HTTP 404"),
        "https://down.example": (lh.UNREACHABLE, None, "ConnectError"),
        "https://wall.example": (lh.BLOCKED_BY_SITE, 403, "HTTP 403"),
    }
    report = lh.scan_links(_refs(*table), checker=lambda u: table[u], sleeper=lambda s: None)
    assert report.by_category() == {lh.OK: 1, lh.BROKEN: 1, lh.UNREACHABLE: 1, lh.BLOCKED_BY_SITE: 1}
    # 403 is NOT actionable (anti-bot walls aren't proof of death).
    assert {r.ref.url for r in report.actionable} == {"https://dead.example", "https://down.example"}


def test_scan_limit() -> None:
    report = lh.scan_links(
        _refs("https://a.example", "https://b.example", "https://c.example"),
        checker=lambda u: (lh.OK, 200, ""),
        sleeper=lambda s: None,
        limit=2,
    )
    assert len(report.results) == 2


def test_scan_pauses_until_clear() -> None:
    calls = {"pause": 0, "slept": 0}

    def should_pause() -> bool:
        calls["pause"] += 1
        return calls["pause"] <= 2  # busy for the first two polls, then clear

    def sleeper(_s: float) -> None:
        calls["slept"] += 1

    report = lh.scan_links(
        _refs("https://a.example"),
        checker=lambda u: (lh.OK, 200, ""),
        sleeper=sleeper,
        should_pause=should_pause,
    )
    assert len(report.results) == 1
    assert calls["slept"] == 2  # slept twice while paused, then proceeded
