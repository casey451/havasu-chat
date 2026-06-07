"""Cache warmer (HANDOFF #5) — read-only DB, public-API POSTs mocked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.chat.llm_cache import make_cache_key
from app.chat.normalizer import normalize
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import ChatLog, LlmResponseCache
from scripts import warm_cache as wc


@pytest.fixture
def db():
    created_logs: list[str] = []
    created_cache: list[str] = []
    with SessionLocal() as session:
        yield session, created_logs, created_cache
        if created_logs:
            session.query(ChatLog).filter(ChatLog.id.in_(created_logs)).delete(
                synchronize_session=False
            )
        if created_cache:
            session.query(LlmResponseCache).filter(
                LlmResponseCache.cache_key.in_(created_cache)
            ).delete(synchronize_session=False)
        session.commit()


def _add_log(db, *, message, role="assistant", tier="3", when=None, normalized=None):
    session, created_logs, _ = db
    row = ChatLog(
        session_id="s",
        message=message,
        role=role,
        tier_used=tier,
        normalized_query=normalized if normalized is not None else message,
        created_at=when or datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(row)
    session.commit()
    created_logs.append(row.id)


def _add_cache_row(db, *, normalized_query, ttl_until):
    session, _, created_cache = db
    key = make_cache_key(normalized_query, {"_today": now_lake_havasu().date().isoformat()})
    row = LlmResponseCache(
        cache_key=key,
        normalized_query=normalized_query,
        context_hash="ctx",
        rubric_version="rv",
        response_text="cached",
        tier_used="tier3",
        ttl_until=ttl_until,
    )
    session.add(row)
    session.commit()
    created_cache.append(key)
    return key


# --- seasonal + dedupe ------------------------------------------------------


def test_load_seasonal_skips_comments_and_blanks(tmp_path):
    p = tmp_path / "warm.txt"
    p.write_text("# header\n\nbest tacos  \n# c\nboat rental\n", encoding="utf-8")
    assert wc.load_seasonal(p) == ["best tacos", "boat rental"]


def test_load_seasonal_missing_file_returns_empty(tmp_path):
    assert wc.load_seasonal(tmp_path / "nope.txt") == []


def test_dedupe_normalizes_dedups_and_caps():
    out = wc.dedupe_normalized(
        ["Best Tacos", "best tacos", "", "Boat Rental", "Live Music"], cap=2
    )
    assert out == [normalize("Best Tacos"), normalize("Boat Rental")]
    assert len(out) == 2


# --- gather_db_queries ------------------------------------------------------


# Unique token so these stay hermetic against other tests' chat_logs rows in
# the shared SQLite DB (filter the global top-N down to our own rows).
_TOK = "zzwarmcache"


def test_gather_orders_by_frequency_and_filters(db):
    session, *_ = db
    popular, rare = f"{_TOK} popular", f"{_TOK} rare"
    for _ in range(3):
        _add_log(db, message=popular, normalized=popular)
    _add_log(db, message=rare, normalized=rare)
    # Excluded: wrong role, wrong tier, too old.
    _add_log(db, message=f"{_TOK} user", role="user", normalized=f"{_TOK} user")
    _add_log(db, message=f"{_TOK} tier1", tier="1", normalized=f"{_TOK} tier1")
    _add_log(
        db, message=f"{_TOK} ancient", normalized=f"{_TOK} ancient",
        when=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=40),
    )
    out = wc.gather_db_queries(session, days=14, limit=100000)
    mine = [q for q in out if q.startswith(_TOK)]
    assert mine.index(popular) < mine.index(rare)  # most frequent first
    assert f"{_TOK} user" not in out
    assert f"{_TOK} tier1" not in out
    assert f"{_TOK} ancient" not in out


def test_gather_accepts_tier3_string(db):
    session, *_ = db
    q = f"{_TOK} legacy tier"
    _add_log(db, message=q, tier="tier3", normalized=q)
    assert q in wc.gather_db_queries(session, days=14, limit=100000)


# --- is_cached (read-only) --------------------------------------------------


def test_is_cached_true_for_unexpired_and_does_not_write(db):
    session, *_ = db
    key = _add_cache_row(db, normalized_query="warm me", ttl_until=datetime.now(UTC) + timedelta(days=1))
    assert wc.is_cached(session, "warm me") is True
    # Read-only: no hit_count bump (default 0 stays 0).
    session.expire_all()
    row = session.query(LlmResponseCache).filter(LlmResponseCache.cache_key == key).one()
    assert row.hit_count == 0


def test_is_cached_false_for_expired(db):
    session, *_ = db
    _add_cache_row(db, normalized_query="stale", ttl_until=datetime.now(UTC) - timedelta(days=1))
    assert wc.is_cached(session, "stale") is False


def test_is_cached_false_for_missing(db):
    session, *_ = db
    assert wc.is_cached(session, "never seen this query") is False


# --- CLI --------------------------------------------------------------------


def test_dry_run_lists_and_never_posts(capsys):
    # Patch gather so the CLI test doesn't depend on global chat_logs state.
    q = normalize(f"{_TOK} dry q")
    with patch.object(wc, "gather_db_queries", return_value=[q]), \
            patch.object(wc, "load_seasonal", return_value=[]), \
            patch.object(wc, "warm_one") as warm:
        rc = wc.main(["--dry-run", "--max-queries", "5"])
    assert rc == 0
    warm.assert_not_called()
    assert q in capsys.readouterr().out


def test_main_warms_uncached_and_skips_cached(db):
    fresh = normalize(f"{_TOK} fresh q")
    cached = normalize(f"{_TOK} cached q")
    _add_cache_row(db, normalized_query=cached, ttl_until=datetime.now(UTC) + timedelta(days=1))
    with patch.object(wc, "gather_db_queries", return_value=[fresh, cached]), \
            patch.object(wc, "load_seasonal", return_value=[]), \
            patch.object(wc, "warm_one", return_value=("3", 123)) as warm:
        rc = wc.main(["--max-queries", "10", "--rps", "0"])
    assert rc == 0
    warmed = [c.args[1] for c in warm.call_args_list]
    assert fresh in warmed
    assert cached not in warmed  # skipped via read-only cache check


def test_bad_max_queries_returns_2():
    assert wc.main(["--max-queries", "0"]) == 2
