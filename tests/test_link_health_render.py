"""F4 follow-up: confirmed-dead outbound links are suppressed at render time.

The link-health sweep flags a broken URL (``LinkHealth.confirmed_broken``); the
Calendar view-model then drops the href so the row renders as plain text instead
of shipping a dead ``<a>`` to users. Covers the pure helpers plus an end-to-end
check that a flagged curated feed link (family_venues) loses its link on the
/events-ui day builder while an unflagged one keeps it.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import LinkHealth
from app.home import events_views as ev
from app.home import family_venues
from app.monitoring import link_health

# A curated funzone venue that renders its hours (and outbound link) on every
# day, so the day builder always includes it regardless of Event seeding.
_MR_LUCKYS_URL = "https://mrluckysbilliardsaz.com/"
_DAY = date(2099, 9, 15)  # far-future, deterministic; no real events needed


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe(db: Session):
    db.query(LinkHealth).filter(LinkHealth.url == _MR_LUCKYS_URL).delete()
    db.flush()
    yield
    db.rollback()


# --- pure helpers ----------------------------------------------------------- #
def test_suppress_dead_links_nulls_only_dead() -> None:
    dead = frozenset({"https://dead.example/"})
    tree = [
        {
            "key": "events",
            "rows": [
                {"title": "Bad", "url": "https://dead.example/"},
                {"title": "Good", "url": "https://ok.example/"},
                {"title": "Internal", "url": "/events/abc"},
            ],
            "subgroups": [
                {"rows": [{"title": "NestedBad", "url": "https://dead.example/"}]}
            ],
        }
    ]
    link_health.suppress_dead_links(tree, dead)
    rows = tree[0]["rows"]
    assert rows[0]["url"] is None  # dead → suppressed
    assert rows[1]["url"] == "https://ok.example/"  # live → kept
    assert rows[2]["url"] == "/events/abc"  # internal permalink → always kept
    assert tree[0]["subgroups"][0]["rows"][0]["url"] is None  # nested dead → suppressed


def test_suppress_dead_links_empty_set_is_noop() -> None:
    row = {"url": "https://anything.example/"}
    link_health.suppress_dead_links([row], frozenset())
    assert row["url"] == "https://anything.example/"


def test_curated_outbound_links_includes_venues() -> None:
    links = dict(family_venues.curated_outbound_links())
    # Mr. Lucky's is a curated funzone venue with a real site.
    assert _MR_LUCKYS_URL in links
    # Every entry is an external http(s) URL (no internal/relative links).
    assert all(u.startswith("http") for u in links)


# --- DB-backed read + end-to-end render ------------------------------------- #
def _flag_broken(db: Session, url: str) -> None:
    db.add(
        LinkHealth(
            url=url,
            kind="feed_venue",
            category=link_health.BROKEN,
            http_status=404,
            confirmed_broken=True,
        )
    )
    db.flush()


def test_confirmed_broken_urls_reads_flag(db: Session) -> None:
    assert _MR_LUCKYS_URL not in link_health.confirmed_broken_urls(db)
    _flag_broken(db, _MR_LUCKYS_URL)
    assert _MR_LUCKYS_URL in link_health.confirmed_broken_urls(db)


def _urls_by_title(sections: list[dict]) -> dict[str, object]:
    """Flatten every row's (title -> url) across sections/subgroups/children."""
    out: dict[str, object] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "title" in node and "url" in node:
                out[node["title"]] = node["url"]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)

    walk(sections)
    return out


def test_events_ui_suppresses_confirmed_dead_feed_link(db: Session) -> None:
    # Baseline: Mr. Lucky's renders WITH its outbound link.
    before = _urls_by_title(ev.calendar_day_view_model(db, day=_DAY)["sections"])
    assert before.get("Mr. Lucky's Billiards & Pub") == _MR_LUCKYS_URL

    # Flag it dead → the day builder must drop the href (render as plain text).
    _flag_broken(db, _MR_LUCKYS_URL)
    after = _urls_by_title(ev.calendar_day_view_model(db, day=_DAY)["sections"])
    assert after.get("Mr. Lucky's Billiards & Pub", "MISSING") is None

    # A different curated venue that is NOT flagged keeps its link (no over-reach).
    other = {t: u for t, u in after.items() if isinstance(u, str) and u.startswith("http")}
    assert other, "expected other venues to still carry their outbound links"
