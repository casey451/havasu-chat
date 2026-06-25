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


# --- concurrency (workers > 1) --------------------------------------------- #
def test_scan_workers_parallel_checks_each_once() -> None:
    refs = _refs(*(f"https://h{i}.example" for i in range(10)))
    report = lh.scan_links(
        refs, checker=lambda u: (lh.OK, 200, "HTTP 200"), sleeper=lambda s: None, workers=4
    )
    assert len(report.results) == 10
    assert {r.ref.url for r in report.results} == {r.url for r in refs}


# --- persistence + confirm-over-time (real test DB) ------------------------ #
def _report(url: str, category: str, code, detail: str) -> lh.ScanReport:
    ref = lh.LinkRef(url, "provider_website", "pX", "Test Co")
    return lh.ScanReport(results=[lh.LinkResult(ref, category, code, detail)])


def _persist(url, category, code, detail, now):
    from app.db.database import SessionLocal

    with SessionLocal() as db:
        newly = lh.persist_results(db, _report(url, category, code, detail), now=now)
        out = (len(newly), newly[0].url if newly else None)
        db.commit()
    return out


def _row(url):
    from app.db.database import SessionLocal
    from app.db.models import LinkHealth

    with SessionLocal() as db:
        return db.query(LinkHealth).filter(LinkHealth.url == url).one_or_none() and {
            "cf": db.query(LinkHealth).filter(LinkHealth.url == url).one().consecutive_failures,
            "confirmed": db.query(LinkHealth).filter(LinkHealth.url == url).one().confirmed_broken,
            "last_ok": db.query(LinkHealth).filter(LinkHealth.url == url).one().last_ok_at,
        }


def _cleanup(url):
    from app.db.database import SessionLocal
    from app.db.models import LinkHealth

    with SessionLocal() as db:
        db.query(LinkHealth).filter(LinkHealth.url == url).delete()
        db.commit()


def test_persist_confirms_only_after_threshold() -> None:
    from datetime import datetime

    url = "https://broken-test.example/x"
    t = datetime(2026, 6, 25, 12, 0, 0)
    try:
        n1, _ = _persist(url, lh.BROKEN, 404, "HTTP 404", t)
        assert n1 == 0 and _row(url)["cf"] == 1 and _row(url)["confirmed"] is False
        n2, who = _persist(url, lh.BROKEN, 404, "HTTP 404", t)
        assert n2 == 1 and who == url and _row(url)["confirmed"] is True
        n3, _ = _persist(url, lh.BROKEN, 404, "HTTP 404", t)  # already confirmed -> not "newly"
        assert n3 == 0
    finally:
        _cleanup(url)


def test_persist_recovery_resets_streak() -> None:
    from datetime import datetime

    url = "https://recovers-test.example/y"
    t = datetime(2026, 6, 25, 12, 0, 0)
    try:
        _persist(url, lh.BROKEN, 500, "HTTP 500", t)
        _persist(url, lh.BROKEN, 500, "HTTP 500", t)
        assert _row(url)["confirmed"] is True
        _persist(url, lh.OK, 200, "HTTP 200", t)  # recovered
        r = _row(url)
        assert r["cf"] == 0 and r["confirmed"] is False and r["last_ok"] is not None
    finally:
        _cleanup(url)


def test_persist_blocked_by_site_never_confirms() -> None:
    from datetime import datetime

    url = "https://wall-test.example/z"
    t = datetime(2026, 6, 25, 12, 0, 0)
    try:
        _persist(url, lh.BLOCKED_BY_SITE, 403, "HTTP 403", t)
        _persist(url, lh.BLOCKED_BY_SITE, 403, "HTTP 403", t)
        r = _row(url)
        assert r["cf"] == 0 and r["confirmed"] is False  # anti-bot is not "broken"
    finally:
        _cleanup(url)
