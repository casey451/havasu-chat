"""Pre-launch deep event verification — three layers, DB-free, cold-fetch only.

Verifies the LIVE public site against authoritative sources, so it needs no
database: everything is derived from cold, cookie-less requests to the running
site plus a re-fetch of each event's origin. That makes it run identically on a
laptop (no local prod DB) and as a nightly CI cron (no DB secret).

  LAYER 1 — source re-verification. For every live event whose start_date is in
  [today, +DAYS_SOURCE], re-fetch its source URL and field-compare date/time/
  venue against what the site shows. A source that can't be re-confirmed (dead
  link, redirect to a generic home page, a changed date) → a quarantine proposal;
  a changed time → a fix proposal.

  LAYER 2 — the full app.events.lint battery over the same window (the existing
  AM/PM-flip, venue-hours, P&R-facility, landmark rules PLUS the pre-launch
  additions: weekday-in-title, season-out-of-season, generic/address venue,
  missing time, ALL-CAPS title, category↔keyword contradiction).

  LAYER 3 — a render sweep: cold-curl every day page for the next DAYS_RENDER,
  plus /family/camps, /night, and /movies?date for the next MOVIES_DAYS. Per
  page it asserts: build-sha == the running build; every event row has a working
  link (no unlinked plain-text rows); a time label (or explicit all-day); a
  non-generic venue; and the section header count matches the rendered row count.

Outputs (to --out-dir, default relay/prelaunch/):
  discrepancies.csv   — one row per Layer-1/Layer-2 finding, with proposed_action
  render_digest.md    — a per-day one-line digest + Layer-3 anomaly detail
  launch_gate.md      — PASS/FAIL scorecard against the launch-gate definition

Exit code is non-zero when the launch gate FAILS, so a CI run turns red.

    python scripts/prelaunch_verify.py --base-url https://askhava.com
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time as _time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.events.lint import (  # noqa: E402
    generic_venue_reason,
    is_kids_series,
    lint_event,
    suspect_showtime,
)

_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
# A row with one of these (or an empty label) is UNFINISHED — no real time and not
# an explicit all-day/hours label. "Hours vary"/"All day" ARE labels, so they pass.
_UNFINISHED_TIME_LABELS = {"", "time tbd", "tbd", "tba"}


# ── source classification ─────────────────────────────────────────────────────
# (domain-substring, source label, per_event_expected). per_event_expected=False
# marks a booking/landing domain whose stored URL is a venue page, not a specific
# event page — a reachable landing is EXPECTED there (not a defect), and deep
# field-diff for those connectors is the CI connector re-run's job.
_SOURCE_MAP: list[tuple[str, str, bool]] = [
    ("allevents.in", "allevents", True),
    ("golakehavasu.com", "go_lake_havasu", True),
    ("riverscenemagazine.com", "river_scene", True),
    ("graceartslive.com", "grace_arts", True),
    ("momence.com", "momence", True),
    ("register.lhcaz.gov", "webtrac", False),
    ("lhcaz.gov", "parks_rec/city", False),
    ("legistar.com", "legistar/city", True),
    ("lakehavasu.altitudetrampolinepark.com", "altitude", False),
    ("altitudetrampolinepark.com", "altitude", False),
    ("usabmx.com", "lhc_bmx", False),
    ("havasulanesaz.com", "bowling", False),
    ("lakehavasupickleball.com", "pickleball", False),
    ("ironwolfgcc.com", "golf_ironwolf", False),
    ("lakehavasufarmersmarket.com", "farmers_market", False),
    ("havasuchamber.com", "chamber", True),
    ("jotform.com", "form", False),
]


# Origins that return an INTERMITTENT 404/challenge to a bot UA (observed flapping
# 404<->200 run-to-run — e.g. usabmx). A dead-link reading here is not trustworthy,
# so it routes to review (verify via the connector's own fetch), never an
# auto-quarantine, and it keeps the nightly cron from false-alarming on flakiness.
_FLAKY_SOURCE_DOMAINS = frozenset({"usabmx.com"})


def _is_flaky_domain(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower().replace("www.", "")
    return any(host == d or host.endswith("." + d) for d in _FLAKY_SOURCE_DOMAINS)


def classify_source(url: str) -> tuple[str, bool]:
    host = (urlparse(url).netloc or "").lower().replace("www.", "")
    for needle, label, per_event in _SOURCE_MAP:
        if needle in host:
            return label, per_event
    if host.endswith(".org") or host.endswith(".com") or host.endswith(".net"):
        return "other", True
    return "unknown", True


# ── catalog model ─────────────────────────────────────────────────────────────
@dataclass
class CatEvent:
    event_id: str
    title: str
    start: datetime | None
    end: datetime | None
    all_day: bool
    location: str  # ICS LOCATION (often an address)
    description: str
    url: str
    categories: str
    recurring: bool
    source: str = ""
    per_event_source: bool = True
    render_venue: str | None = None  # rendered .em (a NAMED place)
    render_time: str | None = None

    @property
    def start_date(self) -> date | None:
        return self.start.date() if self.start else None

    @property
    def venue_for_lint(self) -> str | None:
        """The NAMED venue the page shows (render .em) if we harvested it, else the
        ICS LOCATION. The generic/address-venue lint needs the name, not the raw
        address the feed stores."""
        return self.render_venue if self.render_venue is not None else (self.location or None)


# ── ICS parsing ───────────────────────────────────────────────────────────────
def _unfold(raw: str) -> str:
    return re.sub(r"\n[ \t]", "", raw.replace("\r\n", "\n"))


def _ics_field(block: str, name: str) -> str:
    m = re.search(rf"^{name}(?:;[^:]*)?:(.*)$", block, re.M)
    return m.group(1) if m else ""


def _parse_ics_dt(line: str) -> tuple[datetime | None, bool]:
    """Parse a DTSTART/DTEND value line into (naive datetime, all_day)."""
    if not line:
        return None, False
    if "VALUE=DATE" in line or re.fullmatch(r"\d{8}", line.strip()):
        m = re.search(r"(\d{8})", line)
        if m:
            return datetime.strptime(m.group(1), "%Y%m%d"), True
        return None, False
    m = re.search(r"(\d{8}T\d{6})", line)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S"), False
    return None, False


def parse_feed(text: str) -> list[CatEvent]:
    raw = _unfold(text)
    out: list[CatEvent] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", raw, re.S):
        uid = _ics_field(block, "UID")
        eid = uid.split("@", 1)[0] if uid else ""
        ds = re.search(r"^DTSTART(?:;[^:]*)?:(.*)$", block, re.M)
        de = re.search(r"^DTEND(?:;[^:]*)?:(.*)$", block, re.M)
        start, all_day = _parse_ics_dt(ds.group(1) if ds else "")
        end, _ = _parse_ics_dt(de.group(1) if de else "")
        url = _ics_field(block, "URL").strip()
        src, per_event = classify_source(url)
        out.append(
            CatEvent(
                event_id=eid,
                title=_unescape_ics(_ics_field(block, "SUMMARY")),
                start=start,
                end=end,
                all_day=all_day,
                location=_unescape_ics(_ics_field(block, "LOCATION")),
                description=_unescape_ics(_ics_field(block, "DESCRIPTION")),
                url=url,
                categories=_ics_field(block, "CATEGORIES"),
                recurring=bool(re.search(r"^RRULE:", block, re.M)),
                source=src,
                per_event_source=per_event,
            )
        )
    return out


def _unescape_ics(s: str) -> str:
    return s.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").replace("\\\\", "\\").strip()


# ── render-page parsing + Layer 3 ─────────────────────────────────────────────
_UUID_RE = re.compile(r"^/events/([0-9a-f-]{36})$")
_ID_HREF_RE = re.compile(r"/events/([0-9a-f-]{36})")


@dataclass
class RenderRow:
    href: str | None
    title: str
    venue: str
    time_label: str
    is_pageless: bool
    event_id: str | None
    section: str


@dataclass
class PageResult:
    key: str
    build_sha: str | None
    ok: bool
    anomalies: list[str] = field(default_factory=list)
    section_counts: dict[str, int] = field(default_factory=dict)
    rows: list[RenderRow] = field(default_factory=list)


def _text(node: object) -> str:
    return node.get_text(" ", strip=True) if node else ""  # type: ignore[union-attr]


def parse_render_page(html: str, key: str) -> PageResult:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one('meta[name="build-sha"]')
    build = meta.get("content") if meta else None
    res = PageResult(key=key, build_sha=build, ok=True)
    for sec in soup.select(".sec"):
        hd = sec.select_one(".sechd")
        rows = sec.select(".ev")
        if not rows:
            continue
        hdtext = _text(hd)
        m = re.search(r"(\d+)\s*$", hdtext)
        header_count = int(m.group(1)) if m else None
        secname = re.sub(r"\s*\d+\s*$", "", hdtext).strip() or key
        res.section_counts[secname] = len(rows)
        if header_count is not None and header_count != len(rows):
            res.anomalies.append(
                f"COUNT_MISMATCH[{secname}]: header says {header_count}, {len(rows)} rows rendered"
            )
        for r in rows:
            classes = r.get("class") or []
            href = r.get("href")
            pageless = (r.name != "a") or ("pageless" in classes) or not href
            evt = r.select_one(".evt") or r.select_one(".times") or r.select_one(".tpill")
            time_label = _text(evt)
            title = _text(r.select_one(".et")) or _text(r.select_one(".mt"))
            venue = _text(r.select_one(".em"))
            mid = _ID_HREF_RE.search(href or "")
            row = RenderRow(
                href=href,
                title=title,
                venue=venue,
                time_label=time_label,
                is_pageless=pageless,
                event_id=mid.group(1) if mid else None,
                section=secname,
            )
            res.rows.append(row)
            label = f"{secname}/{title[:40]!r}"
            is_movie = "movie" in classes or "movie" in secname.lower()
            # A class-series row embeds its venue in the title ("Beginner · Black Belt
            # Academy") and links to the provider page — not an unlinked/venue-less defect.
            is_series = (" · " in title) or ("/provider/" in (href or ""))
            if pageless:
                res.anomalies.append(f"UNLINKED_ROW: {label} has no working link (plain-text row)")
            if time_label.strip().lower() in _UNFINISHED_TIME_LABELS and not is_movie:
                res.anomalies.append(f"MISSING_TIME_LABEL: {label} has no time label")
            if not venue and not is_movie and not is_series:
                res.anomalies.append(f"MISSING_VENUE: {label} has no venue")
            elif venue and generic_venue_reason(venue):
                res.anomalies.append(f"GENERIC_VENUE: {label} -> {generic_venue_reason(venue)}")
    res.ok = not res.anomalies
    return res


_CLOCK_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap]m)", re.IGNORECASE)


def _parse_clock(txt: str) -> time | None:
    m = _CLOCK_RE.search(txt or "")
    if not m:
        return None
    h = int(m.group(1)) % 12
    if m.group(3).lower() == "pm":
        h += 12
    return time(h, int(m.group(2)))


def parse_movies_page(html: str, key: str) -> PageResult:
    """The /movies?date layout is film CARDS (article.mvfilm) with .tpill showtimes,
    not the .sec/.ev day-page rows. Assert every film has showtimes and that no
    showtime is implausibly early (the Moana '4 AM' AM/PM-flip class)."""
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one('meta[name="build-sha"]')
    res = PageResult(key=key, build_sha=meta.get("content") if meta else None, ok=True)
    films = soup.select("article.mvfilm") or soup.select("[class*=mvfilm]")
    res.section_counts["films"] = len(films)
    pill_total = 0
    for f in films:
        title = _text(f.select_one(".mvtitle") or f.find(["h2", "h3"]))
        pills = f.select(".tpill")
        pill_total += len(pills)
        if not pills and "no showtime" not in _text(f).lower():
            res.anomalies.append(f"MISSING_SHOWTIMES: film {title[:40]!r} has no showtimes")
        kids = is_kids_series(title)
        for p in pills:
            clk = _parse_clock(_text(p))
            if clk and suspect_showtime(clk, kids_series=kids):
                res.anomalies.append(
                    f"SUSPECT_SHOWTIME: {title[:30]!r} @ {_text(p)} — implausibly early (AM/PM flip?)")
    res.section_counts["showtimes"] = pill_total
    res.ok = not res.anomalies
    return res


# ── Layer 1: source re-verify ─────────────────────────────────────────────────
def _iso_to_dt(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            try:
                return datetime.fromisoformat(m.group(1))
            except ValueError:
                return None
    return None


def extract_jsonld_event(html: str) -> dict | None:
    for blk in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(blk)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and "@graph" in data:
            items = data["@graph"]
        for it in items:
            if isinstance(it, dict) and "Event" in str(it.get("@type", "")):
                return it
    return None


def _norm_venue(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def verify_source(client: httpx.Client, ev: CatEvent) -> dict:
    """Re-fetch + field-compare, then DOUBLE-CONFIRM any quarantine verdict. Many
    origins (usabmx, some Cloudflare sites) return an intermittent 404/challenge to
    a bot UA, so a single dead-link reading is not proof the event is gone — we
    re-fetch once and downgrade to a flaky-source review unless both agree."""
    res = _verify_once(client, ev)
    if res["proposed_action"] != "quarantine":
        return res
    _time.sleep(1.0)
    res2 = _verify_once(client, ev)
    if res2["proposed_action"] != "quarantine":
        res2["proposed_action"] = "review"
        res2["detail"] = f"FLAKY_SOURCE: quarantine-worthy on 1st fetch, reachable on recheck ({res2['detail']})"
        return res2
    res["detail"] = res["detail"] + " [confirmed on recheck]"
    return res


def _verify_once(client: httpx.Client, ev: CatEvent) -> dict:
    """Re-fetch the event's source and field-compare. Returns a finding dict
    (status classification + any mismatched fields + proposed_action)."""
    res: dict = {
        "event_id": ev.event_id, "date": ev.start_date, "title": ev.title,
        "source": ev.source, "layer": "1-source", "field": "", "site_value": "",
        "source_value": "", "detail": "", "proposed_action": "",
    }
    if not ev.url:
        res.update(field="source_url", detail="no source URL on the event",
                   proposed_action="review")
        return res
    try:
        r = client.get(ev.url)
    except Exception as e:
        res.update(field="fetch", detail=f"DEAD_LINK: {type(e).__name__}",
                   proposed_action="quarantine" if ev.per_event_source else "review")
        return res
    orig_path = urlparse(ev.url).path.rstrip("/")
    per_event_link = bool(orig_path and orig_path not in ("", "/"))
    final_path = urlparse(str(r.url)).path.rstrip("/")
    if r.status_code >= 400:
        if r.status_code in (404, 410):
            if _is_flaky_domain(ev.url):
                res.update(field="fetch", site_value=ev.url, source_value=f"HTTP {r.status_code}",
                           detail=f"FLAKY_SOURCE: HTTP {r.status_code} on a known-flaky origin — verify via connector",
                           proposed_action="review")
            else:
                res.update(field="fetch", site_value=ev.url, source_value=f"HTTP {r.status_code}",
                           detail=f"DEAD_LINK: HTTP {r.status_code} (source gone)",
                           proposed_action="quarantine" if per_event_link else "review")
        else:  # 401/403/429/5xx — bot-block or transient, NOT proof the event is gone
            res.update(field="fetch", site_value=ev.url, source_value=f"HTTP {r.status_code}",
                       detail=f"UNREACHABLE: HTTP {r.status_code} (bot-block/transient — recheck)",
                       proposed_action="review")
        return res
    if final_path in ("", "/"):
        if per_event_link:
            res.update(field="fetch", site_value=ev.url, source_value=str(r.url),
                       detail="REDIRECTED_HOME: per-event link now lands on a home page",
                       proposed_action="quarantine")
        else:
            res.update(field="provenance", site_value=ev.url,
                       detail="SOURCE_IS_HOMEPAGE: provenance is only a site homepage (weak, not per-event)",
                       proposed_action="review")
        return res
    node = extract_jsonld_event(r.text)
    if not node:
        if ev.per_event_source:
            res.update(field="schema", detail="UNVERIFIABLE: 200 but no Event schema to compare",
                       proposed_action="review")
        else:
            res.update(field="", detail="connector_landing_ok (reachable; deep diff = CI re-run)",
                       proposed_action="")
        return res
    # We have a JSON-LD Event — compare date, time, venue.
    src_start = _iso_to_dt(str(node.get("startDate", "")))
    if src_start and ev.start:
        if src_start.date() != ev.start.date():
            res.update(field="date", site_value=str(ev.start.date()),
                       source_value=str(src_start.date()),
                       detail="DATE_MISMATCH: source shows a different date",
                       proposed_action="quarantine")
            return res
        if src_start.hour or src_start.minute:
            if (src_start.hour, src_start.minute) != (ev.start.hour, ev.start.minute):
                res.update(field="start_time", site_value=ev.start.strftime("%H:%M"),
                           source_value=src_start.strftime("%H:%M"),
                           detail="TIME_MISMATCH: source shows a different start time",
                           proposed_action="fix_time")
                return res
    loc = node.get("location") or {}
    src_venue = loc.get("name") if isinstance(loc, dict) else (loc if isinstance(loc, str) else "")
    site_venue = ev.render_venue or ev.location
    if src_venue and site_venue:
        a, b = _norm_venue(src_venue), _norm_venue(site_venue)
        title_tokens = set(_norm_venue(ev.title).split())
        src_tokens = set(a.split())
        # Skip when the source's JSON-LD "location" is really the event NAME (a common
        # go_lake_havasu data quirk) — the site venue is the trustworthy one there.
        source_venue_is_title = bool(src_tokens) and src_tokens.issubset(title_tokens)
        if not source_venue_is_title and a and b and a not in b and b not in a \
                and not (set(a.split()) & set(b.split())):
            res.update(field="venue", site_value=site_venue, source_value=src_venue,
                       detail="VENUE_MISMATCH: source names a different venue",
                       proposed_action="review_venue")
            return res
    res.update(detail="OK: source re-confirmed", proposed_action="")
    return res


# ── Layer 2: lint ─────────────────────────────────────────────────────────────
_RULE_ACTION = {
    "ampm_flip": "fix_time", "venue_hours_as_event": "review_row",
    "venue_not_facility": "review_venue", "landmark_venue_mismatch": "review_venue",
    "weekday_mismatch": "review_date", "season_out_of_season": "review_date",
    "generic_venue": "review_venue", "missing_time": "add_time",
    "allcaps_title": "fix_title", "category_keyword_contradiction": "review_category",
}


def lint_catalog_event(ev: CatEvent) -> list[dict]:
    shim = SimpleNamespace(
        title=ev.title, description=ev.description,
        start_time=ev.start.time() if (ev.start and not ev.all_day) else None,
        end_time=ev.end.time() if ev.end else None,
        location_name=ev.venue_for_lint or "",
        date=ev.start_date, category=ev.categories,
        tags=[t for t in ev.categories.split(",") if t],
        source=ev.source, event_url=ev.url, all_day=ev.all_day,
    )
    out = []
    for f in lint_event(shim):
        out.append({
            "event_id": ev.event_id, "date": ev.start_date, "title": ev.title,
            "source": ev.source, "layer": "2-lint", "field": f.rule,
            "site_value": "", "source_value": "", "detail": f.detail,
            "proposed_action": _RULE_ACTION.get(f.rule, "review"),
        })
    return out


# ── driver ────────────────────────────────────────────────────────────────────
def _fetch(client: httpx.Client, url: str) -> tuple[int, str, str]:
    try:
        r = client.get(url)
        return r.status_code, r.text, str(r.url)
    except Exception as e:
        return 0, f"__ERROR__ {type(e).__name__}: {e}", url


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pre-launch deep event verification (DB-free).")
    p.add_argument("--base-url", default="https://askhava.com")
    p.add_argument("--days-source", type=int, default=30, help="Layer 1+2 window")
    p.add_argument("--days-render", type=int, default=21, help="Layer 3 day-page window")
    p.add_argument("--movies-days", type=int, default=7)
    p.add_argument("--gate-days", type=int, default=14, help="launch-gate window")
    p.add_argument("--today", default="", help="override today (YYYY-MM-DD) for tests")
    p.add_argument("--out-dir", default="relay/prelaunch")
    p.add_argument("--timeout", type=float, default=25.0)
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    base = args.base_url.rstrip("/")
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    src_end = today + timedelta(days=args.days_source)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(
        headers={"User-Agent": _UA}, follow_redirects=True, timeout=args.timeout,
    )

    # running build sha (authoritative)
    running_sha = None
    sc, body, _ = _fetch(client, f"{base}/health")
    if sc == 200:
        try:
            running_sha = json.loads(body).get("build_sha")
        except Exception:
            pass
    print(f"running build_sha: {running_sha}")

    # catalog
    sc, feed_text, _ = _fetch(client, f"{base}/events.ics")
    if sc != 200:
        print(f"FATAL: /events.ics returned {sc}", file=sys.stderr)
        return 2
    catalog = parse_feed(feed_text)
    in_window = [e for e in catalog if e.start_date and today <= e.start_date <= src_end and not e.recurring]
    print(f"catalog: {len(catalog)} live events; {len(in_window)} in [{today}, {src_end}] (non-recurring)")

    # Layer 3 render sweep + harvest render venue/time for in-window events.
    # Capped at --days-render (NOT max'd with --days-source): the source window can
    # now span all upcoming events (a nightly cron widened it to ~15 months to catch
    # far-future dead links), but rendering hundreds of day pages is both heavy and
    # pointless — venue harvest only helps near-term rows, and events past the render
    # horizon simply fall back to the ICS LOCATION for Layer-1 venue comparison.
    render_days = args.days_render
    day_dates = [today + timedelta(days=i) for i in range(render_days + 1)]

    def _grab_day(d: date) -> tuple[date, PageResult | None]:
        sc, html, _ = _fetch(client, f"{base}/events-ui?date={d.isoformat()}")
        if sc != 200:
            return d, None
        return d, parse_render_page(html, f"day:{d.isoformat()}")

    pages: dict[date, PageResult] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for d, pr in ex.map(_grab_day, day_dates):
            if pr:
                pages[d] = pr

    render_by_id: dict[str, RenderRow] = {}
    for pr in pages.values():
        for row in pr.rows:
            if row.event_id and row.event_id not in render_by_id:
                render_by_id[row.event_id] = row
    for ev in in_window:
        rr = render_by_id.get(ev.event_id)
        if rr:
            ev.render_venue = rr.venue
            ev.render_time = rr.time_label

    # /family/camps, /night, /movies?date
    extra_pages: dict[str, PageResult] = {}
    for key, path in (("family/camps", "/family/camps"), ("night", "/night")):
        sc, html, _ = _fetch(client, f"{base}{path}")
        extra_pages[key] = parse_render_page(html, key) if sc == 200 else PageResult(
            key=key, build_sha=None, ok=False, anomalies=[f"FETCH_FAILED: HTTP {sc}"])
    movie_pages: dict[date, PageResult] = {}
    for i in range(args.movies_days):
        d = today + timedelta(days=i)
        sc, html, _ = _fetch(client, f"{base}/movies?date={d.isoformat()}")
        movie_pages[d] = parse_movies_page(html, f"movies:{d.isoformat()}") if sc == 200 else PageResult(
            key=f"movies:{d.isoformat()}", build_sha=None, ok=False, anomalies=[f"FETCH_FAILED: HTTP {sc}"])

    # build-sha staleness check across all rendered pages
    for coll, label in ((pages, "day"), (movie_pages, "movies")):
        for d, pr in coll.items():
            if running_sha and pr.build_sha and pr.build_sha != running_sha:
                pr.anomalies.append(f"STALE_BUILD_SHA: page {pr.build_sha} != running {running_sha}")
                pr.ok = False
    for pr in extra_pages.values():
        if running_sha and pr.build_sha and pr.build_sha != running_sha:
            pr.anomalies.append(f"STALE_BUILD_SHA: page {pr.build_sha} != running {running_sha}")
            pr.ok = False

    # Layer 1 (concurrent) + Layer 2
    def _verify(ev: CatEvent) -> dict:
        _time.sleep(0.02)
        return verify_source(client, ev)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        layer1 = list(ex.map(_verify, in_window))
    layer1_findings = [f for f in layer1 if not f["detail"].startswith(("OK", "connector_landing_ok"))]

    layer2_findings: list[dict] = []
    for ev in in_window:
        layer2_findings.extend(lint_catalog_event(ev))

    findings = layer1_findings + layer2_findings
    client.close()

    _write_outputs(out_dir, today, args, running_sha, catalog, in_window,
                   findings, pages, extra_pages, movie_pages, render_days)

    # launch gate
    gate_end = today + timedelta(days=args.gate_days)
    gate_findings = [
        f for f in findings
        if f["date"] and today <= f["date"] <= gate_end
        and f["proposed_action"] in ("quarantine", "fix_time", "add_time", "review_date")
    ]
    render_fails = sum(len(pr.anomalies) for pr in list(pages.values())[: args.days_render + 1])
    render_fails += sum(len(pr.anomalies) for pr in extra_pages.values())
    render_fails += sum(len(pr.anomalies) for pr in movie_pages.values())
    gate_pass = not gate_findings and render_fails == 0
    print(f"\nLAUNCH GATE ({args.gate_days}d): {'PASS' if gate_pass else 'FAIL'} — "
          f"{len(gate_findings)} blocking finding(s), {render_fails} render anomaly(ies)")
    print(f"artifacts → {out_dir}/discrepancies.csv, render_digest.md, launch_gate.md")
    return 0 if gate_pass else 1


def _write_outputs(out_dir, today, args, running_sha, catalog, in_window, findings,
                   pages, extra_pages, movie_pages, render_days) -> None:
    # discrepancies.csv
    cols = ["event_id", "date", "title", "source", "layer", "field",
            "site_value", "source_value", "detail", "proposed_action"]
    with (out_dir / "discrepancies.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for f in sorted(findings, key=lambda x: (str(x["date"]), x["proposed_action"], x["source"])):
            w.writerow({k: ("" if f.get(k) is None else f.get(k, "")) for k in cols})

    # render_digest.md
    lines = [f"# Render sweep digest — {today} (build {running_sha})", ""]
    lines.append("## Day pages")
    for d in sorted(pages):
        pr = pages[d]
        counts = " ".join(f"{k.split()[0].lower()}={v}" for k, v in pr.section_counts.items())
        mark = "OK" if not pr.anomalies else f"{len(pr.anomalies)} ANOMALY"
        within = "assert" if (d - today).days <= args.days_render else "harvest"
        lines.append(f"- {d} [{within}] {counts}  — {mark}")
        for a in pr.anomalies:
            lines.append(f"    - {a}")
    lines.append("\n## /family/camps · /night")
    for key, pr in extra_pages.items():
        lines.append(f"- {key}: {'OK' if not pr.anomalies else str(len(pr.anomalies)) + ' ANOMALY'}")
        for a in pr.anomalies:
            lines.append(f"    - {a}")
    lines.append("\n## /movies?date")
    for d in sorted(movie_pages):
        pr = movie_pages[d]
        counts = " ".join(f"{k}={v}" for k, v in pr.section_counts.items()) or "(no rows)"
        lines.append(f"- {d}: {counts} — {'OK' if not pr.anomalies else str(len(pr.anomalies)) + ' ANOMALY'}")
        for a in pr.anomalies:
            lines.append(f"    - {a}")
    (out_dir / "render_digest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # launch_gate.md
    by_action: dict[str, int] = {}
    for f in findings:
        by_action[f["proposed_action"] or "none"] = by_action.get(f["proposed_action"] or "none", 0) + 1
    gl = [f"# Launch gate scorecard — {today}", "",
          f"- Catalog: {len(catalog)} live events; {len(in_window)} in [{today}, "
          f"{today + timedelta(days=args.days_source)}] (non-recurring)",
          f"- Layer 1+2 findings: {len(findings)}", ""]
    gl.append("## Findings by proposed action")
    for act, n in sorted(by_action.items(), key=lambda x: -x[1]):
        gl.append(f"- {act}: {n}")
    gl.append("\n## By source")
    src_counts: dict[str, int] = {}
    for f in findings:
        src_counts[f["source"]] = src_counts.get(f["source"], 0) + 1
    for s, n in sorted(src_counts.items(), key=lambda x: -x[1]):
        gl.append(f"- {s}: {n}")
    (out_dir / "launch_gate.md").write_text("\n".join(gl) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
