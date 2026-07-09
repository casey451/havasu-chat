"""Visual fidelity gate for the home + calendar redesign (M6).

Two guards:

1. **No horizontal overflow at 390px** (hard, deterministic — the DoD mobile-fit
   rule). Fails if the flagged /home or /calendar scrolls sideways on a phone.

2. **Pixel-drift self-baseline.** Captures the flagged /home and /calendar at
   390x844 and 1280x1024 and pixel-diffs them against a per-environment baseline
   under ``tests/visual/baseline/`` (gitignored). First run bootstraps the
   baseline (no assertion); later runs fail if drift exceeds ``VISUAL_TOLERANCE``
   (default 0.1%). This catches unintended CSS regressions during development.
   The committed, agreed-design references live in ``tests/visual/refs/`` (from
   ``capture_refs.py``) for human comparison — a direct pixel-diff of the live
   page against the mockup is intentionally NOT asserted because the production
   page renders real, time-varying data (different events/dates) that the static
   mockup cannot match.

Skipped unless ``RUN_VISUAL=1`` and a Chromium build is available, so the default
``pytest -n auto`` CI job never depends on a browser. The dedicated
``visual-regression.yml`` workflow installs Chromium and sets ``RUN_VISUAL=1``.
Set ``UPDATE_VISUAL_BASELINE=1`` to (re)write baselines.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest

if os.getenv("RUN_VISUAL") != "1":
    pytest.skip("visual gate: set RUN_VISUAL=1 to run", allow_module_level=True)

uvicorn = pytest.importorskip("uvicorn")
playwright_api = pytest.importorskip("playwright.sync_api")
PIL_image = pytest.importorskip("PIL.Image")

from PIL import Image, ImageChops  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app.main import app  # noqa: E402

_HERE = Path(__file__).resolve().parent
_BASELINE = _HERE / "baseline"
_DIFF = _HERE / "diff"
_TOLERANCE = float(os.getenv("VISUAL_TOLERANCE", "0.001"))  # 0.1% changed pixels
_SIZES = {"mobile": (390, 844), "desktop": (1280, 1024)}
_PAGES = {"home": "/home?home_redesign=1", "calendar": "/calendar?home_redesign=1"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server() -> str:
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    assert srv.started, "uvicorn did not start"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)


def _drift_fraction(a: Path, b: Path) -> float:
    img_a = Image.open(a).convert("RGB")
    img_b = Image.open(b).convert("RGB")
    if img_a.size != img_b.size:
        return 1.0
    diff = ImageChops.difference(img_a, img_b)
    bbox = diff.getbbox()
    if bbox is None:
        return 0.0
    # count pixels whose max channel delta exceeds a small noise threshold
    changed = 0
    total = img_a.size[0] * img_a.size[1]
    for px in diff.crop(bbox).getdata():
        if max(px) > 12:
            changed += 1
    return changed / total


def test_redesign_visual(server: str) -> None:
    _BASELINE.mkdir(parents=True, exist_ok=True)
    _DIFF.mkdir(parents=True, exist_ok=True)
    update = os.getenv("UPDATE_VISUAL_BASELINE") == "1"
    failures: list[str] = []
    overflow: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page_name, path in _PAGES.items():
            for size_name, (w, h) in _SIZES.items():
                # reduced-motion freezes the infinite sheen + entrance so the
                # pixel-diff is stable run-to-run (the CSS disables them there).
                page = browser.new_page(
                    viewport={"width": w, "height": h}, reduced_motion="reduce"
                )
                page.goto(server + path, wait_until="networkidle")
                page.wait_for_timeout(400)
                # 1) mobile-fit: no sideways scroll
                if w <= 430:
                    sw = page.evaluate("document.documentElement.scrollWidth")
                    iw = page.evaluate("window.innerWidth")
                    if sw > iw + 1:
                        overflow.append(f"{page_name}@{w}px scrollWidth={sw} > innerWidth={iw}")
                # 2) pixel-drift self-baseline
                shot = _HERE / f"_cur_{page_name}_{size_name}.png"
                page.screenshot(path=str(shot), full_page=True)
                base = _BASELINE / f"{page_name}_{size_name}.png"
                if update or not base.exists():
                    shot.replace(base)
                else:
                    frac = _drift_fraction(base, shot)
                    if frac > _TOLERANCE:
                        failures.append(f"{page_name}_{size_name} drift {frac:.4%} > {_TOLERANCE:.2%}")
                    shot.unlink(missing_ok=True)
                page.close()
        browser.close()

    assert not overflow, "Horizontal overflow at 390px: " + "; ".join(overflow)
    assert not failures, "Visual drift: " + "; ".join(failures)


# ── Desktop wide-width shell guard (2026-07-09) ──────────────────────────────
# The audit's declared blind spot (§5) was that nothing tested above ~540px, so
# the wide-monitor layout was never verified. This deterministic guard runs the
# home + calendar at 1280 and 1920 and asserts the centered-shell invariants:
#
#   * the shell (``.rd-shell``) caps content width (≤ ~1300px) and stays centered;
#   * no structural block escapes the shell horizontally.
#
# The second check is load-bearing and NOT redundant with a scrollWidth check:
# the bug it guards against (a bare ``1fr`` feed track blowing out and shoving
# the rail off the right edge) was *clipped by* ``body{overflow-x:hidden}``, so
# ``scrollWidth <= innerWidth`` still held — only the rail's own box, at
# ``right`` far beyond the shell, betrayed it. So we assert on the boxes of the
# structural wrappers directly, not on document scroll width.
_DESKTOP_SIZES = {"desktop": (1280, 1024), "wide": (1920, 1080)}

# Structural blocks that must live inside the shell on any page that has them.
_SHELL_CHILDREN = [
    ".cond", ".daystrip", ".main", ".sections", ".rail", ".foot", ".calbar",
    ".evx", ".dirx", ".prof-wrap", ".artx", ".chat-shell", ".todayx", ".acctx",
    ".coll-wrap", ".sponx", ".portx", ".famx", ".grpx",
]

_SHELL_PROBE_JS = """
(sels) => {
  const iw = document.documentElement.clientWidth;
  const shellEl = document.querySelector('.rd-shell');
  if (!shellEl) return {noShell: true};
  const s = shellEl.getBoundingClientRect();
  const offenders = [];
  for (const sel of sels) {
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && (r.right > s.right + 2 || r.left < s.left - 2)) {
        offenders.push(sel + ' L' + Math.round(r.left) + ' R' + Math.round(r.right));
      }
    }
  }
  return {
    iw, shellLeft: Math.round(s.left), shellRight: Math.round(s.right),
    shellWidth: Math.round(s.width), offenders,
  };
}
"""


def test_desktop_shell_layout(server: str) -> None:
    """The centered content shell holds at 1280 and 1920 with nothing escaping it."""
    problems: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page_name, path in _PAGES.items():
            for size_name, (w, h) in _DESKTOP_SIZES.items():
                page = browser.new_page(
                    viewport={"width": w, "height": h}, reduced_motion="reduce"
                )
                page.goto(server + path, wait_until="networkidle")
                page.wait_for_timeout(300)
                res = page.evaluate(_SHELL_PROBE_JS, _SHELL_CHILDREN)
                tag = f"{page_name}@{w}px"
                if res.get("noShell"):
                    problems.append(f"{tag}: no .rd-shell element")
                    page.close()
                    continue
                # shell caps content width (max-width applied, not full-bleed)
                if res["shellWidth"] > 1300:
                    problems.append(f"{tag}: shell width {res['shellWidth']} > 1300")
                # shell is centered within the content area (allow scrollbar slack)
                skew = abs(res["shellLeft"] - (res["iw"] - res["shellRight"]))
                if skew > 4:
                    problems.append(
                        f"{tag}: shell not centered (left={res['shellLeft']} "
                        f"right-gap={res['iw'] - res['shellRight']} skew={skew})"
                    )
                # no structural block escapes the shell (catches the grid blowout)
                if res["offenders"]:
                    problems.append(f"{tag}: escaped shell: {', '.join(res['offenders'])}")
                page.close()
        browser.close()

    assert not problems, "Desktop shell layout: " + " | ".join(problems)
