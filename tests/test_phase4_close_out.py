"""Phase 4.4 — close-out smoke: with_retry wiring + docs + import chain."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


def test_magic_link_path_uses_outbox_enqueue_and_deliver() -> None:
    src = _read_text("app/auth/routes.py")
    assert "enqueue_outbox" in src
    assert "deliver_outbox_row" in src


def test_image_processing_uses_with_retry_in_processor() -> None:
    src = _read_text("app/photos/processor.py")
    assert "from app.core.background import with_retry" in src
    assert "with_retry(" in src


def test_scan_and_save_mentions_scheduled_via_with_retry() -> None:
    src = _read_text("app/api/routes/chat.py")
    assert "from app.core.background import with_retry" in src
    assert "with_retry" in src and "scan_and_save_mentions" in src


def test_enrich_contribution_scheduled_via_with_retry() -> None:
    for rel in (
        "app/api/routes/contribute.py",
        "app/api/routes/admin_contributions.py",
        "app/api/routes/admin_mentions.py",
        "app/admin/mentions_html.py",
    ):
        src = _read_text(rel)
        assert "with_retry, enrich_contribution" in src


def test_hourly_cleanup_loop_unchanged_signature() -> None:
    src = _read_text("app/main.py")
    assert "async def _hourly_cleanup_loop() -> None:" in src
    assert "await asyncio.to_thread(run_expired_review_cleanup)" in src
    assert "await asyncio.to_thread(run_stuck_photo_sweep)" in src


def test_lifespan_starts_hourly_cleanup_via_create_task() -> None:
    src = _read_text("app/main.py")
    assert "asyncio.create_task(_hourly_cleanup_loop())" in src


def test_railway_runbook_exists_nonempty() -> None:
    p = _repo_root() / "docs" / "operations" / "railway_scheduled_jobs_runbook.md"
    assert p.is_file() and len(p.read_text(encoding="utf-8").strip()) > 200


def test_scrape_logs_template_exists_nonempty() -> None:
    p = _repo_root() / "docs" / "operations" / "scrape_logs_template.md"
    assert p.is_file() and len(p.read_text(encoding="utf-8").strip()) > 80


def test_close_out_import_chain_no_gotcha17() -> None:
    repo = _repo_root()
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(repo)!r})\n"
        "from app.core.background import with_retry  # noqa: F401\n"
        "from app.contrib.google_places_scraper import GooglePlacesClient  # noqa: F401\n"
        "from app.contrib.osm_overpass_client import OsmOverpassClient  # noqa: F401\n"
        "from app.contrib.ingest_reconciler import reconcile_hit  # noqa: F401\n"
        "import json\n"
        "print(json.dumps({'models_loaded': 'app.db.models' in sys.modules}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(repo),
        timeout=90,
        env={**os.environ, "AUTH_DEV_MODE": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["models_loaded"] is False
