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
