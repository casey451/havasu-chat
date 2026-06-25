"""Lightweight VPS watchdog: prod health + scraper freshness + disk, email on change.

Designed for a systemd timer on the Hostinger VPS (every ~5 min). It runs the
checks once, compares against the last run's state, and emails **only on a state
transition** (ok->fail or fail->ok) so a steady-state green box is silent and a
new failure -- or a recovery -- pages exactly once.

It reuses the app's own Resend-backed sender (``app.auth.email_sender``) so there
is no SMTP plumbing: set ``RESEND_API_KEY`` + ``RESEND_FROM_ADDRESS`` (the prod
values) and ``WATCH_ALERT_EMAIL`` in the unit's EnvironmentFile. With those unset
it runs **log-only** -- safe to install before the secret is in place.

Checks (all read-only; no prod-DB writes, nothing exposed):
  * prod ``/health`` returns 200 with ``db_connected`` truthy
  * the scrape unit's last run exited 0 and is fresher than the cadence + slack
  * disk usage of ``/`` is under the threshold

Config (env, all optional -- sensible defaults):
  WATCH_HEALTH_URL          default https://askhava.com/health
  WATCH_SCRAPER_UNIT        default havasu-vision-scrape.service
  WATCH_SCRAPER_MAX_AGE_H   default 50   (every-other-day cadence = 48h + slack)
  WATCH_DISK_PATH           default /
  WATCH_DISK_PCT_MAX        default 90
  WATCH_STATE_FILE          default /var/lib/havasu-watch/state.json
  WATCH_ALERT_EMAIL         destination; unset -> log-only

Usage:
  python scripts/vps_watch.py            # run the checks, alert on change
  python scripts/vps_watch.py --status   # print current status, never alert
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vps_watch")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


# --------------------------------------------------------------------------- #
# Individual checks (pure where possible; I/O seams are injectable for tests)
# --------------------------------------------------------------------------- #
def check_health(url: str, *, getter=None) -> CheckResult:
    """Prod is healthy iff /health is 200 and reports db_connected truthy."""
    try:
        if getter is None:
            import httpx

            resp = httpx.get(url, timeout=10.0)
            status = resp.status_code
            body = resp.json()
        else:
            status, body = getter(url)
    except Exception as exc:  # network error, bad JSON, timeout
        return CheckResult("health", False, f"request failed: {type(exc).__name__}: {exc}")
    if status != 200:
        return CheckResult("health", False, f"HTTP {status}")
    db_ok = bool((body or {}).get("db_connected", True))
    if not db_ok:
        return CheckResult("health", False, "200 but db_connected=false")
    return CheckResult("health", True, "200, db_connected")


def check_disk(path: str, max_pct: float) -> CheckResult:
    usage = shutil.disk_usage(path)
    pct = usage.used / usage.total * 100.0
    ok = pct < max_pct
    return CheckResult("disk", ok, f"{pct:.0f}% used of {usage.total // 2**30}G (limit {max_pct:.0f}%)")


def _systemctl_show(unit: str) -> dict[str, str]:
    out = subprocess.run(
        ["systemctl", "show", unit, "-p", "Result,ExecMainStatus,ExecMainExitTimestamp,ActiveState"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    props: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return props


def evaluate_scraper(props: dict[str, str], *, max_age_h: float, now: datetime) -> CheckResult:
    """Last scrape run must have exited 0 and be fresher than the cadence + slack."""
    result = props.get("Result", "")
    status = props.get("ExecMainStatus", "")
    ts_raw = props.get("ExecMainExitTimestamp", "")
    if not ts_raw:
        return CheckResult("scraper", False, "no recorded run (ExecMainExitTimestamp empty)")
    if result and result != "success":
        return CheckResult("scraper", False, f"last run Result={result}, ExecMainStatus={status}")
    if status not in ("", "0"):
        return CheckResult("scraper", False, f"last run exit status {status}")
    # ExecMainExitTimestamp looks like: "Thu 2026-06-25 13:35:41 UTC"
    try:
        ts = datetime.strptime(ts_raw, "%a %Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return CheckResult("scraper", True, f"ran ok (unparsed ts {ts_raw!r})")
    age_h = (now - ts).total_seconds() / 3600.0
    if age_h > max_age_h:
        return CheckResult("scraper", False, f"stale: last ok run {age_h:.0f}h ago (limit {max_age_h:.0f}h)")
    return CheckResult("scraper", True, f"ran ok {age_h:.0f}h ago")


def check_scraper(unit: str, *, max_age_h: float, now: datetime) -> CheckResult:
    try:
        props = _systemctl_show(unit)
    except Exception as exc:
        return CheckResult("scraper", False, f"systemctl failed: {type(exc).__name__}: {exc}")
    return evaluate_scraper(props, max_age_h=max_age_h, now=now)


# --------------------------------------------------------------------------- #
# State + alerting
# --------------------------------------------------------------------------- #
def load_state(path: Path) -> dict[str, bool]:
    try:
        return {k: bool(v) for k, v in json.loads(path.read_text()).items()}
    except Exception:
        return {}


def save_state(path: Path, results: list[CheckResult]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({r.name: r.ok for r in results}))
    except Exception:
        logger.warning("could not persist state to %s", path)


def transitions(prev: dict[str, bool], results: list[CheckResult]) -> list[CheckResult]:
    """Checks whose ok-ness changed since last run (new checks count as a change)."""
    changed = []
    for r in results:
        if r.name not in prev or prev[r.name] != r.ok:
            changed.append(r)
    return changed


def _bodies(host: str, results: list[CheckResult], changed: list[CheckResult]) -> tuple[str, str, str]:
    any_fail = any(not r.ok for r in results)
    subject = f"[{'FAIL' if any_fail else 'RECOVERED'}] Ask Hava VPS {host}"
    lines = [f"{'FAIL' if not r.ok else 'ok  '}  {r.name}: {r.detail}" for r in results]
    changed_lines = [f"  - {r.name}: {'FAIL' if not r.ok else 'recovered'} ({r.detail})" for r in changed]
    text = "Changed:\n" + "\n".join(changed_lines) + "\n\nAll checks:\n" + "\n".join(lines) + "\n"
    html = "<h3>Changed</h3><ul>" + "".join(
        f"<li><b>{r.name}</b>: {'FAIL' if not r.ok else 'recovered'} — {r.detail}</li>" for r in changed
    ) + "</ul><h3>All checks</h3><ul>" + "".join(
        f"<li>{'❌' if not r.ok else '✅'} <b>{r.name}</b>: {r.detail}</li>" for r in results
    ) + "</ul>"
    return subject, html, text


def alert(results: list[CheckResult], changed: list[CheckResult], *, host: str, to_email: str | None) -> None:
    subject, html, text = _bodies(host, results, changed)
    if not to_email:
        logger.info("ALERT (log-only, WATCH_ALERT_EMAIL unset): %s | %s", subject, text.replace("\n", " "))
        return
    try:
        from app.auth.email_sender import send_alert_email

        send_alert_email(to_email=to_email, subject=subject, html_body=html, text_body=text)
        logger.info("alert emailed to %s: %s", to_email, subject)
    except Exception as exc:
        logger.warning("email send failed (%s); alert was: %s | %s", exc, subject, text.replace("\n", " "))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_checks(now: datetime | None = None) -> list[CheckResult]:
    now = now or datetime.now(timezone.utc)
    return [
        check_health(os.getenv("WATCH_HEALTH_URL", "https://askhava.com/health")),
        check_scraper(
            os.getenv("WATCH_SCRAPER_UNIT", "havasu-vision-scrape.service"),
            max_age_h=float(os.getenv("WATCH_SCRAPER_MAX_AGE_H", "50")),
            now=now,
        ),
        check_disk(os.getenv("WATCH_DISK_PATH", "/"), float(os.getenv("WATCH_DISK_PCT_MAX", "90"))),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="print status, never alert")
    args = parser.parse_args(argv)

    results = run_checks()
    for r in results:
        logger.info("%s %s: %s", "ok " if r.ok else "FAIL", r.name, r.detail)

    if args.status:
        return 0 if all(r.ok for r in results) else 1

    state_path = Path(os.getenv("WATCH_STATE_FILE", "/var/lib/havasu-watch/state.json"))
    prev = load_state(state_path)
    changed = transitions(prev, results)
    # Don't page on first-ever run if everything is green (no real transition).
    meaningful = [c for c in changed if not (not prev and c.ok)]
    if meaningful:
        host = os.getenv("WATCH_HOST_LABEL", os.uname().nodename if hasattr(os, "uname") else "vps")
        alert(results, changed, host=host, to_email=(os.getenv("WATCH_ALERT_EMAIL") or "").strip() or None)
    save_state(state_path, results)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
