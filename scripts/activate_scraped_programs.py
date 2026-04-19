"""One-off: flip every source='scraped' program to is_active=True.

Two modes:

  db    — default; uses the app's SessionLocal. Works against whatever
          DATABASE_URL the app resolves to. For Railway prod, run under
          `railway run` so Railway injects its DATABASE_URL.

  http  — logs in with ADMIN_PASSWORD, scrapes /admin?tab=programs for
          scraped + inactive rows, then POSTs /admin/programs/{id}/activate
          for each. No DB connection needed.

Usage:
  # Local DB:
  python scripts/activate_scraped_programs.py --dry-run
  python scripts/activate_scraped_programs.py

  # Railway prod DB:
  railway run python scripts/activate_scraped_programs.py --dry-run
  railway run python scripts/activate_scraped_programs.py

  # HTTP against a running server (local or prod):
  ADMIN_PASSWORD=... python scripts/activate_scraped_programs.py \\
      --mode http --base-url https://havasu-chat.up.railway.app --dry-run
  ADMIN_PASSWORD=... python scripts/activate_scraped_programs.py \\
      --mode http --base-url https://havasu-chat.up.railway.app
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ACTIVATE_RE = re.compile(r"/admin/programs/([^/\"']+)/activate")


def _run_db_mode(dry_run: bool) -> int:
    from app.db.database import SessionLocal
    from app.db.models import Program

    with SessionLocal() as db:
        rows = (
            db.query(Program)
            .filter(Program.source == "scraped", Program.is_active.is_(False))
            .all()
        )
        print(f"Found {len(rows)} inactive scraped programs.")
        for p in rows:
            print(f"  - {p.id}  {p.provider_name!r}  {p.title!r}")

        if dry_run:
            print("Dry run — no changes committed.")
            return 0
        if not rows:
            return 0

        for p in rows:
            p.is_active = True
        db.commit()
        print(f"Activated {len(rows)} programs.")
    return 0


def _run_http_mode(base_url: str, password: str, dry_run: bool) -> int:
    import requests
    from bs4 import BeautifulSoup

    base = base_url.rstrip("/")
    s = requests.Session()

    login = s.post(
        f"{base}/admin/login",
        data={"password": password},
        allow_redirects=False,
        timeout=30,
    )
    if login.status_code not in (302, 303) or "admin_session" not in s.cookies.get_dict():
        print(f"Login failed: HTTP {login.status_code}", file=sys.stderr)
        return 2

    page = s.get(f"{base}/admin?tab=programs", timeout=60)
    page.raise_for_status()

    soup = BeautifulSoup(page.text, "html.parser")
    targets: list[tuple[str, str, str]] = []
    for card in soup.select("article.card"):
        if not card.find(string=lambda t: isinstance(t, str) and t.strip() == "Scraped"):
            continue
        form = card.find("form", action=_ACTIVATE_RE)
        if form is None:
            continue
        m = _ACTIVATE_RE.search(form.get("action", ""))
        if not m:
            continue
        pid = m.group(1)
        title_el = card.find("h3")
        title = title_el.get_text(strip=True) if title_el else ""
        provider = ""
        for p in card.select("p.meta"):
            label = p.find("span", class_="label")
            if label and label.get_text(strip=True).lower() == "provider":
                provider = p.get_text(" ", strip=True).removeprefix("Provider").strip()
                break
        targets.append((pid, provider, title))

    print(f"Found {len(targets)} inactive scraped programs.")
    for pid, provider, title in targets:
        print(f"  - {pid}  {provider!r}  {title!r}")

    if dry_run:
        print("Dry run — no POSTs sent.")
        return 0
    if not targets:
        return 0

    activated = 0
    for pid, _, title in targets:
        r = s.post(
            f"{base}/admin/programs/{pid}/activate",
            allow_redirects=False,
            timeout=30,
        )
        if r.status_code in (302, 303):
            activated += 1
        else:
            print(
                f"  ! failed {pid} ({title!r}): HTTP {r.status_code}",
                file=sys.stderr,
            )
    print(f"Activated {activated}/{len(targets)} programs.")
    return 0 if activated == len(targets) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("db", "http"), default="db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="HTTP mode only; defaults to http://localhost:8000",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("ADMIN_PASSWORD", ""),
        help="HTTP mode only; defaults to $ADMIN_PASSWORD",
    )
    args = parser.parse_args()

    if args.mode == "db":
        return _run_db_mode(args.dry_run)

    if not args.password:
        print(
            "HTTP mode requires --password or ADMIN_PASSWORD env var.",
            file=sys.stderr,
        )
        return 2
    return _run_http_mode(args.base_url, args.password, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
