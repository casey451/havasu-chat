"""
Snapshot orchestration for parks-and-rec scrapers.

Each scrape source exposes a ``pull_snapshot()`` callable that returns a
list of plain dict records. The runner invokes each registered source,
writes a timestamped JSON snapshot under ``data/scrapes/<source>/``, and
updates a manifest at ``data/scrapes/manifest.json`` recording the
latest successful run per source.

The runner is fail-soft: a failure in one source does not prevent other
sources from running. Errors are recorded into the manifest.

Loading snapshots into the catalog (Contribution → Event/Program via the
existing approval flow) is a separate step, not done here. This module
intentionally has no DB dependencies — it can run in environments where
``app.db`` is unstable.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PullFn = Callable[[], list[dict[str, Any]]]

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPES_DIR = REPO_ROOT / "data" / "scrapes"
MANIFEST_PATH = SCRAPES_DIR / "manifest.json"


@dataclass
class SnapshotResult:
    source: str
    ok: bool
    record_count: int = 0
    snapshot_path: str | None = None
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""

    def as_manifest_entry(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "record_count": self.record_count,
            "snapshot_path": self.snapshot_path,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class ScrapeRun:
    started_at: str
    finished_at: str
    results: list[SnapshotResult] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"version": 1, "sources": {}, "history": []}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "sources": {}, "history": []}


def _save_manifest(manifest: dict[str, Any]) -> None:
    _ensure_dir(SCRAPES_DIR)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def run_one(source: str, pull: PullFn, *, snapshots_dir: Path = SCRAPES_DIR) -> SnapshotResult:
    started = _now_iso()
    result = SnapshotResult(source=source, ok=False, started_at=started, finished_at=started)
    try:
        records = pull()
        if not isinstance(records, list):
            raise TypeError(f"{source} pull returned {type(records).__name__}, expected list")
        target_dir = snapshots_dir / source
        _ensure_dir(target_dir)
        snap_path = target_dir / f"{_slug_now()}.json"
        snap_path.write_text(
            json.dumps(
                {"source": source, "captured_at": started, "records": records},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        result.ok = True
        result.record_count = len(records)
        result.snapshot_path = str(snap_path.relative_to(REPO_ROOT))
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}"
    finally:
        result.finished_at = _now_iso()
    return result


def run_all(sources: dict[str, PullFn], *, snapshots_dir: Path = SCRAPES_DIR) -> ScrapeRun:
    started = _now_iso()
    results: list[SnapshotResult] = []
    for source, pull in sources.items():
        results.append(run_one(source, pull, snapshots_dir=snapshots_dir))
    finished = _now_iso()
    run = ScrapeRun(started_at=started, finished_at=finished, results=results)

    manifest = _load_manifest()
    manifest.setdefault("sources", {})
    manifest.setdefault("history", [])
    for r in results:
        manifest["sources"][r.source] = r.as_manifest_entry()
    manifest["history"].append(
        {
            "started_at": started,
            "finished_at": finished,
            "summary": {r.source: ("ok" if r.ok else "fail") for r in results},
        }
    )
    # Cap history to the last 100 runs to keep the file small.
    manifest["history"] = manifest["history"][-100:]
    _save_manifest(manifest)
    return run


def latest_snapshot_path(source: str, *, snapshots_dir: Path = SCRAPES_DIR) -> Path | None:
    """Return the path of the newest snapshot for ``source``, or None."""
    d = snapshots_dir / source
    if not d.exists():
        return None
    files = sorted(d.glob("*.json"))
    return files[-1] if files else None


def load_latest_records(source: str, *, snapshots_dir: Path = SCRAPES_DIR) -> list[dict[str, Any]]:
    """Convenience: load records from the newest snapshot of ``source``."""
    p = latest_snapshot_path(source, snapshots_dir=snapshots_dir)
    if p is None:
        return []
    payload = json.loads(p.read_text(encoding="utf-8"))
    recs = payload.get("records") or []
    return list(recs)
