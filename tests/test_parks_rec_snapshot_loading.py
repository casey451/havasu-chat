"""Regression: a seasonal source that legitimately empties must not redden the
parks-rec-scrapes cron.

The aquatic schedule goes empty off-season. scrape_runner still writes a
snapshot (the pull SUCCEEDS with 0 records), so the loader must treat an
empty-but-present snapshot as a clean 0-import — only a TRULY absent snapshot
(the scraper never wrote one) is the "no snapshot found" error. Before the fix
the loader conflated the two and failed the whole cron even though WebTrac
loaded fine (parks-rec-scrapes red on 2026-07-07/09/11).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.contrib.parks_rec_loader import (
    AQUATIC_SOURCE,
    load_latest_snapshots,
)


def _write_snapshot(snapshots_dir: Path, source: str, records: list[dict]) -> None:
    d = snapshots_dir / source
    d.mkdir(parents=True, exist_ok=True)
    (d / "20260711T134429Z.json").write_text(
        json.dumps({"source": source, "captured_at": "2026-07-11T13:44:29Z", "records": records}),
        encoding="utf-8",
    )


def _aquatic(results):
    return next(r for r in results if r.source == AQUATIC_SOURCE)


def test_empty_but_present_aquatic_snapshot_is_benign(tmp_path: Path) -> None:
    # Scraper ran, seasonal source had nothing -> snapshot exists with 0 records.
    _write_snapshot(tmp_path, AQUATIC_SOURCE, [])
    results = load_latest_snapshots(dry_run=True, snapshots_dir=tmp_path)
    aq = _aquatic(results)
    assert aq.errors == []  # not a failure -> cron stays green
    assert aq.considered == 0
    assert aq.imported == 0


def test_absent_aquatic_snapshot_is_still_an_error(tmp_path: Path) -> None:
    # No snapshot file at all -> the scraper never wrote one (real breakage).
    results = load_latest_snapshots(dry_run=True, snapshots_dir=tmp_path)
    aq = _aquatic(results)
    assert aq.errors == ["no snapshot found"]
