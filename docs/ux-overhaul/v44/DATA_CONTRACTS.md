# v4.4 DATA CONTRACTS — sources, fallbacks, honest clocks

Principle everywhere: **one source per fact, an honest clock on it, and omission —
never fabrication — when it's missing.**

## §1 GasService (PR-1, consumed by PR-6)

### 1.1 Shape
```python
@dataclass
class GasStation:
    name: str
    address: str            # short street form, e.g. "14750 S AZ-95"
    directions_url: str
    prices: dict[str, float | None]   # keys: "reg" | "mid" | "prem" | "dsl"
    observed_at: datetime   # per-station price age (UTC)

@dataclass
class GasBoard:
    stations: list[GasStation]        # already filtered: age <= 7 days
    pulled_at: datetime               # last successful pull
    label: str                        # honest tier label, §1.3
    grades_available: list[str]       # subset of ["reg","mid","prem","dsl"]
```
`cheapest(grade, n=None)` returns stations having that grade, ascending, ties keep
pull order. ALL surfaces (strip tile, home panel, /gas) call this and only this.

### 1.2 Source
Extend the existing gas pull to capture every grade the provider exposes. Do not add
a second provider. If the provider exposes regular only, `grades_available == ["reg"]`
and every grade UI collapses (BUILD_PLAN decision 3).

### 1.3 Honest label tiers (exact strings)
| age of `pulled_at`      | label                          |
|-------------------------|--------------------------------|
| < 60 min                | `Updated {m} min ago`          |
| 1–6 h                   | `Updated {h}h ago`             |
| 6–24 h                  | `Updated today {h:%-I:%M %p}` (Phoenix) — if pulled yesterday: `Updated yesterday` |
| 1–7 d                   | `Updated {weekday}`            |
| > 7 d                   | station rows HIDDEN; if the whole board is >7d: render the tile with no price and the panel says `Prices unavailable — we're on it` |
No ceilings like ">4h ago" for week-old data. The label derives from `pulled_at`, not
from a capped bucket.

### 1.4 Failure alerting
Pull failure or silence > 12h → `logger.warning("GAS_PULL_STALE age=%s", age)` once
per hour max. No new infra.

## §2 Counting service (PR-3, consumed by PR-7)

### 2.1 The one base
`day_counts(d: date) -> DayCount` where `DayCount.total` is **exactly what the home
feed renders for that date**: events + class sessions + venue-hours rows + movie
titles (not per-showtime) after the same dedupe/filters `redesign._enrich` applies.
That definition is authoritative because F6 already pinned home's headline and pills
to it; calendar cells and the agenda header now consume the same number.

### 2.2 Callers
home headline/pills (already), calendar month cells (`+N more` = total − chips
rendered), agenda panel header, date-strip dots. One implementation, one cache
(keyed by date, TTL aligned with the feed cache from PR-2).

### 2.3 Dot thresholds (PR-7)
`1–19 → 1 dot · 20–49 → 2 · ≥50 → 3 · 0 → none`. Spark: date ∈ `HEADLINER_DATES`
(config dict, value = tooltip text). Spark replaces dots.

## §3 Conditions additions (PR-4)

### 3.1 Water temperature
USGS NWIS instantaneous JSON, parameter `00010`, site from `WATER_TEMP_USGS_SITE`.
During PR-4, verify the nearest gauge that actually returns 00010 (candidates:
Colorado River below Parker Dam / Lake Havasu area gauges), set it as the default,
record the choice in the PR body. Convert °C→°F, round to whole degrees. Cache 1h.
Value older than 6h or fetch failure → tile omitted. Never estimated.

### 3.2 Sunset (no dependency)
NOAA simplified solar calc, America/Phoenix (no DST). Reference implementation:
```python
import math
from datetime import date, datetime, timedelta, timezone

def sunset_local(d: date, lat=34.4839, lon=-114.3225, tz_offset=-7) -> datetime:
    n = d.toordinal() - date(2000, 1, 1).toordinal() + 0.0008
    Jstar = n - lon / 360
    M = math.radians((357.5291 + 0.98560028 * Jstar) % 360)
    C = 1.9148 * math.sin(M) + 0.02 * math.sin(2 * M) + 0.0003 * math.sin(3 * M)
    lam = math.radians((math.degrees(M) + C + 180 + 102.9372) % 360)
    Jtransit = 2451545.0 + Jstar + 0.0053 * math.sin(M) - 0.0069 * math.sin(2 * lam)
    delta = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
    latr = math.radians(lat)
    cosw = (math.sin(math.radians(-0.833)) - math.sin(latr) * math.sin(delta)) / (
        math.cos(latr) * math.cos(delta))
    w0 = math.acos(max(-1, min(1, cosw)))
    Jset = Jtransit + math.degrees(w0) / 360
    ts = (Jset - 2440587.5) * 86400
    return datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(hours=tz_offset)
```
Unit-test against three known dates (±3 min). Render `%-I:%M` + unit `pm`.
Cache per day. (This can't fail; no fallback needed.)

### 3.3 Tile assembly
`cond_tiles` = temp, water (if fresh), wind, uv (existing color rule), sunset, gas.
Clouds removed. Missing tiles are omitted — the grid flexes (existing CSS).

## §4 Date-keyed caching (PR-2)

Resolve "today" (America/Phoenix) and "this month" BEFORE cache lookup for `/home`,
`/events-ui`, `/calendar` (and any date-scoped render cache). Key shape:
`render:{route}:{resolved_date_or_month}:{variant}`. Never cache a bare-"today" key.
Regression fixtures: the 2026-07-02 observations (home served Jul 1; bare /calendar
served Jun 26 while `?cal=2026-07` was fresh).

## §5 Directory counts (PR-5)

Launcher counts = the same query `/categories` uses per category (cached ≤24h,
single helper). Total = sum across all 16 → rendered as `2,400+` style floor-rounded
hundreds (`f"{total//100*100:,}+"`). The 8 launcher categories map to their existing
category-page URLs; labels per DESIGN_SPEC §4.1.

## §6 News card (PR-5)

Reuse the ticker's stored items (same store the 2026-06-29 ticker reads). Card shows
the 3 most recent; each: headline, `nr-region` chip per the existing §6.2 region rule,
source · relative age. Empty store → no card, no ticker (existing behavior).

## §7 Explicitly out of scope (do not build)

- No DB migrations, no backfills, no admin UI changes.
- No new ad slots or sponsor surfaces beyond the marquee's existing model.
- No recommendation/ranking of businesses anywhere.
- No persistence of the gas grade selection.
- No changes to the events taxonomy/sub-tree logic (calendar two-surface work owns it).
