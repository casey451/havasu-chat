"""run_vision_scrapes.sh self-updates to latest main before scraping (2026-06-25).

Nothing pulled `main` onto the VPS before a scheduled run, so a timer could run
stale code. The script now does a non-fatal `git pull --ff-only` first (toggle
HAVASU_GIT_PULL=0 to skip). These drive the real script against a throwaway git
repo via bash; skipped where bash/git aren't available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "deploy" / "vps-vision" / "run_vision_scrapes.sh"

_BASH = shutil.which("bash")
_GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(
    _BASH is None or _GIT is None, reason="bash + git required"
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run([_GIT, *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_up_to_date_repo(tmp_path: Path) -> Path:
    """A clone whose `main` tracks an up-to-date origin, so `pull --ff-only` is a no-op success."""
    remote = tmp_path / "remote.git"
    _git(["init", "--bare", "-b", "main", str(remote)], tmp_path)
    work = tmp_path / "work"
    _git(["clone", str(remote), str(work)], tmp_path)
    _git(["config", "user.email", "t@example.com"], work)
    _git(["config", "user.name", "Test"], work)
    (work / "f.txt").write_text("hi\n", encoding="utf-8")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "init"], work)
    _git(["push", "-u", "origin", "main"], work)
    return work


def _normalized_script(tmp_path: Path) -> Path:
    """Copy the script with LF endings so bash never trips on a CRLF checkout."""
    dst = tmp_path / "run.sh"
    dst.write_text(SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n"), encoding="utf-8")
    return dst


def _run(script: Path, work: Path, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "HAVASU_REPO_DIR": str(work),
        "HAVASU_PY": "true",  # stub the scrapers (bash builtin: ignores args, exits 0)
    }
    env.update(env_extra)
    return subprocess.run(
        [_BASH, str(script)], capture_output=True, text=True, env=env
    )


def test_self_update_pulls_by_default(tmp_path: Path) -> None:
    work = _make_up_to_date_repo(tmp_path)
    r = _run(_normalized_script(tmp_path), work, {})
    assert r.returncode == 0, r.stderr
    assert "self-update: now at" in r.stdout  # the pull ran and logged the SHA
    assert "git pull failed" not in r.stdout


def test_self_update_skipped_when_disabled(tmp_path: Path) -> None:
    work = _make_up_to_date_repo(tmp_path)
    r = _run(_normalized_script(tmp_path), work, {"HAVASU_GIT_PULL": "0"})
    assert r.returncode == 0, r.stderr
    assert "self-update" not in r.stdout
    assert "git pull failed" not in r.stdout


def test_run_completes_even_if_pull_fails(tmp_path: Path) -> None:
    """A repo with no upstream -> pull fails, but the run is non-fatal and finishes."""
    work = tmp_path / "noremote"
    _git(["init", "-b", "main", str(work)], tmp_path)
    _git(["config", "user.email", "t@example.com"], work)
    _git(["config", "user.name", "Test"], work)
    (work / "f.txt").write_text("hi\n", encoding="utf-8")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "init"], work)

    r = _run(_normalized_script(tmp_path), work, {})
    assert r.returncode == 0, r.stderr
    assert "git pull failed; running existing checkout" in r.stdout
    assert "vision scrape done" in r.stdout  # continued past the failed pull
