# Ask Hava — Master Problem List & Fix Plan (Cowork second pass)

> **⚠ READ THIS FIRST — annotation by the Track B/Cowork session, 2026-06-11 ~03:30:**
> **Do NOT execute §0.1's repair steps.** The "4 truncated templates / 17 NUL'd
> files" finding was the sandbox virtiofs mount serving stale, size-padded views
> of files another session was actively editing — not the state of the Windows
> disk (see CLAUDE.md "the mount lies"). The tree's health was subsequently
> proven by Casey's full local suite (10,17x green ×4 runs), green CI on five
> PRs built from those exact files, and live page verification. "Restoring
> template tails" against the healthy files would CREATE the damage this section
> fears. The one real on-disk corruption (trades.py, a mount-write casualty) was
> caught and fixed the same night.
>
> **Also overtaken by events — #248–#255 merged + deployed 2026-06-10/11:**
> stale footer email (flushed by redeploy) · cafés slug live at
> `/cafes-and-coffee` · gas "Updated {timestamp}" + breadcrumb + average copy ·
> "Add to catalog"→"Add to Hava" · sponsor mailtos + /sponsor↔/portal/advertise
> contradiction · jargon sweep · hero · WS-4 address passes applied to prod.
> §0.2's stale-build/cache evidence largely predates those four deploys —
> re-verify before acting. The genuinely NEW items below (reserve-form category
> taxonomy, double-escaped names, "event has passed" timing, /search raw
> tokens, /group pages, ICS junk titles, page-cache vintage skew) remain real
> and untouched.
>
> **Second update, ~04:30:** Track C's #266 (audit fix batches 1+2) has since
> merged + deployed, covering: event classifier/dedup · privacy renderer ·
> favicon · **reserve-form category taxonomy** · proxy headers. Remaining from
> this list: double-escaped /categories names · "event has passed" timing ·
> /search raw tokens · /group pages · ICS junk titles · page-cache vintage
> skew — re-verify each against live before building, per the lesson above.

Audited: 2026-06-10, ~8:30–9:10 AM MST. Method: full repo inspection (working tree + `git show main:`)
cross-checked against a live crawl of askhava.com (home, events-ui, restaurants leaf, bars leaf,
/lake-havasu/restaurants, provider/love-s, gas, today, map, night, sponsor, portal, portal/advertise,
contribute, privacy, terms, robots, favicon, www).

**HALT note: nothing here is pre-approved. Every item is a proposal. No changes were made in this pass.**

Status tags used throughout:
- `[LIVE-BUG]` broken on production right now, no fix exists yet anywhere
- `[FIXED-TREE]` already fixed in the *uncommitted* working tree — needs commit → PR → Casey merge → deploy
- `[FIXED-BRANCH]` fixed in the 3 commits on `fix/ws4-address-flag-precision` (B1 dedupe / B2 rating-prior+address / WS-4)
- `[OPS]` no code change — Railway env / DNS / deploy / mailbox action, Casey-gated
- `[DATA]` DB content fix (backfill / merge / re-ingest) — dry-run → counts → approval → apply, per CLAUDE.md
- `[DECIDE]` needs a Casey product/copy decision before implementation

---

## 0. STOP FIRST — working-tree damage & deploy pipeline (found during this pass; blocks everything else)

The single most important discovery of this pass: **production is running a stale build, and the
working tree containing the newer fixes is actively being damaged by a concurrent session.**

### 0.1 ~~A parallel session is corrupting this checkout~~ → CORRECTED: mount-view artifact (mostly)

**Correction (same day, verified Windows-side):** the NUL bytes and truncations below were observed
through the Cowork sandbox MOUNT, whose reads CLAUDE.md documents as unreliable ("served stale,
size-padded with trailing NULs, or truncated"). Windows-side `Read` verification shows the real files
are **healthy**: `gas_prices.html` is complete (endif/endblock/footer present, new copy applied),
`sponsor_landing.html` is a fresh 35-line rewrite (the funnel consolidation §6 is already underway by
another agent, with `hello@askhava.com` until the sponsors@ alias exists), `test_wp1_shell.py` reads
normally. **Do NOT run a NUL-stripping pass against this tree based on the list below** — re-verify any
specific file Windows-side first. What WAS real: `.git/index.lock` exists and other agents are actively
editing (contribute.py and sponsor_landing.html changed on the Windows disk mid-audit) — coordinate file
ownership, run git only from Casey's terminal. The original (now mostly-retracted) finding is preserved
below for the record:

### 0.1-original (retracted as written — mount artifacts) `[superseded]`
- `.git/index.lock` exists (another git process holds/held it).
- Files changed *mid-audit*: `contribute.py` title flipped "Add to catalog"→"Add to Hava" between two reads;
  `gas_prices.html` lost its last ~7 lines between two reads.
- **4 templates are now truncated mid-block and fail `jinja2.Environment().parse()`:**
  `home_sandstone.html` (unclosed `block`), `provider_profile.html` (unclosed `for`),
  `events_sandstone.html` (unclosed `if`), `gas_prices.html` (unclosed `if` — `{% endif %}`/`{% endblock %}`
  and the "Prices update once daily" footer line are gone).
- **17 files contain trailing NUL bytes** (`\x00`), which makes git treat them as binary and breaks tooling:
  `app/api/routes/contribute.py` (2), `app/templates/about.html` (7), `collection_landing.html` (3),
  `contact.html` (12), `desert_base.html` (3), `help.html` (6), `login_check_email.html` (33),
  `portal_advertise.html` (6), `sponsor_landing.html` (324), `themed_group_landing.html` (3),
  `today.html` (8), `app/admin_portal/README.md` (312), `docs/privacy.md` (3), `docs/tos.md` (9),
  `docs/phase-8-8-6-step-0-eval-harness-spec.md` (68,571!), `tests/test_phase87_privacy.py` (6),
  `tests/test_wp1_shell.py` (3).
- Consequences: Python refuses to import source files containing NUL → `contribute.py` would 500 the app
  and the two NUL'd test files break `pytest` collection, so the repo's own commit gate
  (`pytest -q` green) currently cannot pass from this tree.

**Fix:** (1) Casey confirms the other session is stopped; (2) remove stale `.git/index.lock`;
(3) strip trailing NULs from all 17 files (`python - <<'py'` one-liner: read bytes, `rstrip(b'\x00 \t\r\n')`
+ re-append single `\n`); (4) restore the 4 truncated template tails from the last good state
(`git diff` each against `main`, re-apply only the *intended* edits — the intended edits are documented
in §10 below so nothing is lost); (5) `python -m pytest -q` + `ruff check .` must pass before anything
else proceeds.

### 0.2 Production is a stale build `[OPS]` — explains a whole class of "bugs"
Evidence gathered live:
- `main` already contains `SecurityHeadersMiddleware` (HSTS, Referrer-Policy, Permissions-Policy,
  `Cache-Control: no-cache` on HTML) and `CanonicalHostRedirectMiddleware` — but the 2026-06-09 audit saw
  only `x-frame-options`/`x-content-type-options` live, and the no-cache behavior is visibly absent.
- Different pages served different cache vintages within minutes: conditions strip showed
  UV 0.5 / UV 2 / UV 10 / UV 0.1 across four consecutive page fetches; `/today` says
  "as of 7:06 PM" while its own tiles say "Updated 5 min ago".
- The **stale footer email** (`hello@havasuchat.com`) appears on `/gas` and
  `/categories/eat-and-drink/restaurants` while `/home`, `/privacy`, `/terms`, `/night` show the correct
  `hello@askhava.com` — same template, different cache age. The repo template has been correct since the
  rename (`desert_base.html`, "Report wrong info" link).
- Recent commit history includes "fix(build): pin Python 3.13.13 — unpinned version broke Railway build",
  i.e., deploys were failing at some point.

**Fix:** check Railway → confirm the latest `main` deploy actually succeeded; redeploy; purge any
edge/proxy cache. Then re-verify: response headers include `Referrer-Policy` + `Cache-Control: no-cache`,
and the `/gas` footer email is correct. Most of the "stale footer" / frozen-conditions sightings should
disappear with this single action.

### 0.3 Railway env still serves the old hero `[OPS]`
`HOME_HERO_HEADLINE` env var on Railway overrides the template default, so prod renders
"Ask Hava. Anything in Havasu." + eyebrow "Ask Hava — your local concierge" (name 4× before any promise).
The working tree's new default is hero B: "Search like a local." + "Hava knows every launch ramp, taco
stand, and plumber in Lake Havasu City." with eyebrow = date and the name only on the button.
**Fix:** unset `HOME_HERO_EYEBROW` / `HOME_HERO_HEADLINE` on Railway (or set them to the chosen copy)
at the same time the template deploy goes out. `[DECIDE: final hero copy — A/B/C from the copy audit]`

### 0.4 Uvicorn doesn't trust the proxy scheme `[LIVE-BUG]` — one flag, three symptoms
`Procfile`: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — **no `--proxy-headers`**, so behind
Railway's TLS-terminating proxy `request.url.scheme == "http"` inside the app. This single root cause produces:
1. Provider JSON-LD `"url": "http://askhava.com/..."` (template uses raw `request.url`);
2. HSTS never emitted (middleware gates on `request.url.scheme == "https"`);
3. Any future `request.url`-based absolute URL will leak http.
**Fix:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`
(both `Procfile` and the `[start] cmd` in `nixpacks.toml`). Independently, also fix the template to use
the canonical URL (see §4.1) so JSON-LD is correct even if env regresses.
(Auth cookies are safe either way — `cookie_secure_in_prod()` is env-based, not scheme-based.)

---

## 1. P0 — trust-damaging / revenue-blocking

### 1.1 Old domain `havasuchat.com` in trust-critical places
| Where | Evidence | Status |
|---|---|---|
| `/sponsor` "Get in touch" + visible email → `sponsors@havasuchat.com` | `app/templates/sponsor_landing.html:42-43`; confirmed live | `[DECIDE]+[OPS]` — PR checklist says deliberately left pending the `sponsors@askhava.com` alias decision (docs/PROMPT_COWORK_FOLLOWUP_2026-06-10.md:60). Create the alias/forward first, then swap both hrefs + visible text. If /sponsor is 301'd per §6 this page disappears anyway — but fix the mailto regardless in case of direct links. |
| `/terms` §1: "By using Hava (havasuchat.com — the website…)" | `docs/tos.md:9`; confirmed live | `[LIVE-BUG]` → change to askhava.com, bump "Last updated". |
| Event-ingest fallback URL `https://havasuchat.com/events` | `app/contrib/event_ingest.py:205,352` — **neither audit caught this**; it writes the dead domain into stored events' `event_url` when a source has no URL | `[LIVE-BUG]` → change fallback to `https://askhava.com/events-ui` (or store `None` and let the permalink omit the link) + `[DATA]` backfill existing Event rows whose `event_url` LIKE '%havasuchat%'. |
| Script UA strings reference havasuchat/railway URLs | `scripts/schedule_drift_check.py:51`, `app/contrib/url_fetcher.py:20`, `app/contrib/reddit_havasu.py:37` | Cosmetic `[LIVE-BUG]`, low priority — update UA contact URLs to askhava.com. |
| Stale footer `hello@havasuchat.com` on live /gas + /categories/… | cache vintage, not code — see §0.2 | `[OPS]` redeploy/purge, then spot-check. |

### 1.2 /privacy bullets broken mid-sentence (every wrapped bullet) `[LIVE-BUG]`
Root cause precisely located: `_render_doc_markdown_to_html()` in `app/main.py` (~line 209ff) emits one
`<li>` per *source line*; the continuation line of a hard-wrapped bullet falls through to the paragraph
branch, which first closes the open `<ul>`. Live output is exactly
`<ul><li>**Your chat messages…** — to improve the</li></ul><p>service, fix bugs…</p>` for ~12 bullets.
**Fix (do both):** (a) in the `- ` branch, keep consuming following lines while the *raw* line starts
with whitespace and isn't a new `- ` / heading / blank, joining them into the same `<li>`;
(b) unwrap the bullets in `docs/privacy.md` anyway (source hygiene). Add a unit test rendering a wrapped
bullet. Then eyeball every bullet on live /privacy and /terms.
Bonus found in same renderer: HTML comments pass straight through to output — the live /terms page source
ships `<!-- Drafted by AI 2026-06-07 — needs attorney review before commercial launch. -->` (tos.md line 1).
Strip comment lines in the renderer (or delete the comment) — that note should not be publicly visible.

### 1.3 "Board of Adjustment Meeting" filed under Music & nightlife `[LIVE-BUG]` — root cause found
`app/home/sandstone.py` `_event_tier()` matches hint keywords **as substrings**: `_MUSIC_HINTS` contains
`"dj"`, and "a**dj**ustment" contains it. Confirmed live: the meeting is the sole "Music & nightlife 1"
item on /events-ui *and* (because MUSIC outranks COMMUNITY/OTHER) it's today's **top headline on the
home week strip**.
**Fix:**
1. Word-boundary matching for all hint lists (`re.search(rf"\\b{re.escape(h)}\\b", joined)` — precompile).
   Same latent bug class: "spin" in "inspiring", "fish" in "selfish", "fest" in "manifest", "club" in "club house".
2. Add civic hints routed to Community: `council, commission, board of adjustment, city of, public hearing,
   board meeting, government` (checked *before* music).
3. Review-queue rule from the original audit: flag titles matching `government|council|board|commission`
   for human confirmation.
4. Unit tests: "Board of Adjustment Meeting"→community, "DJ Night"→music, "Inspiring Watercolors"→not water/music.

### 1.4 Duplicate listings — far bigger than "Broken Yolk ×2" `[DATA]` + `[FIXED-BRANCH tooling]`
Confirmed on ONE page (restaurants leaf): Broken Yolk Cafe ★4.7(35) + The Broken Yolk (both 440 El Camino Way).
**New this pass — visible dup clusters on the same page:** Denny's ×2 (1620 McCulloch), Niko's Grill & Pub ×2
(2690 N Kiowa), Hangar 24 ×2 (5600 AZ-95 / 5600 Hwy 95 N — also exhibits the route-name inconsistency),
Rosati's ×2 (91 London Bridge), Shugrue's ×3 (Restaurant and Brewery Group / Restaurant & Bar / Bridgeview Room),
Sloane's ×2 (2198 McCulloch), Dos Amigos ×2 (2231 McCulloch #107), Filiberto's ×2 (35 N Lake Havasu),
Montana's ×2 (3301 Maricopa), Turtle Grille ×2 (1000 McCulloch), The Spot ×2 (3612 Jamaica),
Bad Miguel's ×2 (1841 Kiowa #103), Reflections ×2 (Iron Wolf), Lin's Little China / "Lina Little China",
Rusty's ×2, McKee's ×2 (bars leaf). The bars leaf tail strip even renders **Ghost Mine Saloon twice in a row**.
**Fix:** the B1 commit already ships dedupe-resolution paths + merge 301s (`/provider/{loser}` 301s to the
winner — verified in `app/providers/router.py`) and `scripts/merge_place_id_duplicates.py`. So:
(1) merge B1/B2 to main first; (2) run a systematic dedup pass keyed on (normalized name tokens +
normalized street number/street) and on shared `place_id`; (3) follow prod-data rules — dry-run, show
cluster counts, Casey approves, apply; (4) re-crawl sitemap-providers.xml for surviving (name, address) pairs.

### 1.5 Cactus arms upside down on /portal/advertise `[LIVE-BUG]` — fix verified geometrically
`app/templates/portal_advertise.html:72-78`. Current: left arm `rect x=316 y=210 h=34` hangs below its
elbow (`x=318 y=210`); right arm `rect x=348 y=222 h=26` hangs below elbow (`x=334 y=222`).
The original audit's corrected coordinates are right — I re-derived them: left arm `y=186` (spans 186–220,
overlapping the elbow's 210–220 band), right arm `y=206` (spans 206–232, overlapping 222–232):
```svg
<g fill="#11324d">
  <rect x="330" y="196" width="14" height="80" rx="7"/>   <!-- trunk: unchanged -->
  <rect x="316" y="186" width="10" height="34" rx="5"/>   <!-- left arm: was y=210 -->
  <rect x="318" y="210" width="24" height="10" rx="5"/>   <!-- left elbow: unchanged -->
  <rect x="348" y="206" width="10" height="26" rx="5"/>   <!-- right arm: was y=222 -->
  <rect x="334" y="222" width="22" height="10" rx="5"/>   <!-- right elbow: unchanged -->
</g>
```
Left arm top (186) sits above the y=196 horizon line; reads fine as foreground silhouette (sun's bottom
edge is y=150, no collision). Screenshot mobile + desktop after.

### 1.6 No favicon anywhere `[LIVE-BUG]`
`/favicon.ico` 404s live; `desert_base.html` `<head>` has zero icon/manifest tags (also missing on the
hand-built /contribute page and the legacy chat shell if any). **Fix:** generate from the sun logo mark:
`favicon.ico` (16/32/48), `icon.svg`, `apple-touch-icon.png` (180), `manifest.webmanifest` + 192/512 PNGs,
`<meta name="theme-color">` (sandstone/orange). Add the `<link>` set to `desert_base.html` head AND the
standalone heads (`contribute.py` HTML, `privacy_doc` inherits base, event_permalink inherits base).
Serve `/favicon.ico` at the root path (static mount covers `/static/...`; add an explicit route or place
the file so the root path resolves).

### 1.7 Provider address garbled + poisoned JSON-LD `[FIXED-BRANCH — verify]`
Live Love's: "14875 AZ-95, Lake Havasu City, AZ 86404, USA, Lake Havasu City, AZ 86404" — the stored
`postal_address.street` holds the FULL Google-formatted address, then the template appends city/state/zip
again (`provider_profile.html` Good-to-know row + `streetAddress` in JSON-LD).
The B2/WS-4 branch commits touch exactly this (`app/core/address.py`, `app/providers/queries.py`,
`tests/test_address_street_line.py`, plus `scripts/fix_address_quality.py` and an address-quality admin
queue; `address_quality_snapshot_20260611T012838Z.json` shows a prod scan was already run, with a noted
lesson about 268 false-positive HOLDs).
**Action:** verify the branch's `derive_postal_address()` parses street-only on the Love's fixture, merge,
deploy, then `[DATA]` run the mechanical fix script (dry-run → counts → approval), then validate JSON-LD
in Google's Rich Results test.

---

## 2. Events pipeline

### 2.1 Class/event duplication on /events-ui `[LIVE-BUG]` — two distinct gaps
Live today: Lap Swim, Motion & Mobility, Tai Chi, Arthritis, Aqua Aerobics, Deep Water Fit each appear
**twice** (dated Event row + "Runs regularly ↻" Schedule row).
- Gap A — Event-vs-Schedule: `drop_event_duplicates()` (`app/events/class_occurrences.py:109-116`) matches
  on EXACT `(title.lower(), date)`; the two pipelines title the same class differently
  ("Motion & Mobility **Margie**" vs "Motion & Mobility"; "Tai Chi **Vince**" vs "Tai Chi **(Aquatic)**").
  **Fix:** match on normalized titles (reuse `normalize_event_title` + strip instructor-name suffixes /
  parentheticals / time-day tokens) with a fuzzy fallback (`rapidfuzz` already a dependency —
  `events/dedup.py` uses threshold 85) **scoped to same date + same venue + start_time within ±15 min**,
  so "Lap Swim" vs "Lap Swim (Morning)" at the same pool dedupes but two different venues' "Yoga" don't.
- Gap B — Schedule-vs-Schedule (**new this pass**): both Havasu Pilates rows are Schedule rows —
  "9:00 AM Beginner Pilates (Wed/Fri)" AND "Beginner Reformer Pilates - 9:00 AM Wed/Fri" — the captured
  schedule import stored the same class twice with title variants (every Pilates slot ×2).
  **Fix:** dedupe at import/publish time on (entity, weekday-set, start_time) + title similarity;
  `[DATA]` one-off cleanup of existing duplicate Schedule rows for Havasu Pilates (and scan all venues:
  `SELECT entity_id, days_of_week, start_time, COUNT(*) ... HAVING COUNT(*)>1`).

### 2.2 Time/day tokens baked into titles `[LIVE-BUG]`
Live: "9 AM **9:00 AM Beginner Pilates (Wed/Fri)**", "4 PM Polymer Clay Jewelry **4-5:30pm**",
"Inferno **(6 AM)**", "Rec Gym **(Wed 4 PM)**", "Hot Fusion (8:30 AM)" — the page then prefixes its own
time label, so time shows 2–3×. **Fix:** a `clean_event_title()` applied at ingest (scrapers/base.py) and
at schedule-import: strip leading/trailing time ranges (`\b\d{1,2}(:\d{2})?\s*(am|pm)\b`, `\d-\d:\d\d?pm`),
day-list parentheticals (`\((Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^)]*\)`), and time-parentheticals — but KEEP
genuinely distinguishing names. `[DATA]` backfill existing titles with the same function (dry-run diff list first).

### 2.3 Junk in event titles (calendar) `[LIVE-BUG]` + `[DATA]`
Confirmed live on home month grid: "Fit & Flex **(155)** Stephanie" (mystery number — likely a room/course
code from the parks-rec source; strip `\(\d+\)` tokens), "Baby Sitting Class **June 6**" and
"Pickleball Round Robin **June 25**" (dates in titles — strip trailing month-day when it equals the event
date), "Free Family Swim **Sponsored by: Abundant Grace Church Event is limited to the first 400 people**"
(description crammed into title — truncate title at first sentence/sponsor marker, move remainder to
description), "Summer Free Movies **"Spongebob Square Pants"** **Star Cinemas**" (venue in title + correct
spelling is "SpongeBob SquarePants"), "Rowdy Bingo **at Grapes N Grains**" while the venue line repeats
the same venue (strip trailing "at {venue}" when it matches location_name), instructor-name suffixes
("Motion & Mobility Margie") — strip when the token matches a known instructor list per venue.
Implement in the same `clean_event_title()`; add a small fixture test per pattern.

### 2.4 Inconsistent/dead link targets `[LIVE-BUG]`
Dated events → `/events/{uuid}` ✓; venue classes → `/provider/{slug}` ✓; but classes whose venue has **no
provider page** link to `/events-ui` itself (self-link dead end — live: all Havasu Pilates rows).
Root: `ClassOccurrence.url` fallback (`app/events/class_occurrences.py:47-51`).
**Fix:** render non-slug classes as non-links (template branch on `row.url`), or create the missing
provider (Havasu Pilates Studio exists as an entity but has no active provider). Pick one behavior; the
non-link render is the safe default and the template already has a no-link card pattern.

### 2.5 One counting rule `[LIVE-BUG]` — proven divergence
Home week strip "12 events · 41 classes" vs /events-ui "Events 4 + Music 1 + Classes 48" — same day, both
sum to 53. Cause: `week_strip()` counts `event_count = all one-off rows` and `class_count = recurring +
schedule rows` (`app/home/sandstone.py` ~line 406), while `/events-ui` groups by `_group_for_tier()` which
sends class-TIER one-offs ("Beginner Pilates" one-off rows) into Classes.
**Fix:** make `week_strip()` (and `calendar_month()` cell counts) classify via the same
`_group_for_tier(tier, recurring=…)` used by `events_views.py`; events = events+music+water(+community)
groups, classes = classes group. Add a test asserting home day-summary == events-ui group sums for a
seeded day.

### 2.6 Legends `[FIXED-TREE partially]`
Live home week-strip legend says "Festival / special …" while the month legend says "Special event …";
tree already unifies the NAME to "Special event". Remaining inconsistency: week legend has 5 entries,
month has 3 — but month pills genuinely only render special/water/class (`_event_pill_type()` uses tags
only). Either (a) give month cells the same 5-type `_event_css_type()` so the legends can match, or
(b) accept different sets but add the missing "Community"/"Music" pill types to month. Also fix
`_event_pill_type()` defaulting untagged non-featured one-offs to a **class** pill (a one-off market event
wears "Class / ongoing" on the month grid — misleading; default should be the special/event color).

### 2.7 Events SEO `[LIVE-BUG]`
- No Event JSON-LD anywhere: add `Event` schema to `/events/{id}` permalink (template already has the
  fields: title, date/time, venue, image, description) and an `ItemList` of `Event` on `/events-ui` day view.
  Free rich-results win for a hyperlocal events product.
- /events-ui meta description is the generic homepage one live; tree already has the events-specific one ✓
  (`events_sandstone.html:3`) — deploy.

### 2.8 Events group label `[DECIDE]`
First accordion group is literally labeled "Events" ("Events 4"). Rename to "Around town" (audit
suggestion) in `GROUP_DEFS` (`app/home/events_views.py:52`) — label only, key stays `events`.

---

## 3. Directory data quality (beyond the dup clusters in §1.4)

### 3.1 Wrong-subcategory chips on leaf pages `[LIVE-BUG]` + `[DATA]`
Restaurants page shows chips: Lighthouse Lounge / Niko's / Hangar 24 / Tavern 95 / Place To Be / McKee's /
Martini Bay / Legendz / Gallagher's / Turtle Grille → "Bars Breweries"; ChaBones (steakhouse!) /
Shugrue's / Reflections / **BlondZee's Steak House (new)** → "Cafes Coffee"; Ed's Deli → "Quick Bites";
Albertsons Deli + Pit Stop Deli → "Specialty"; **Western States Restaurant Consulting → "Professional"**
(a consulting firm on the restaurants page). Bars page mirror-images it: Waters Edge Winery → "Restaurants",
Lake Havasu Cigars → "Specialty".
Three separate fixes:
1. **Leaf listing filter:** rows whose `subcategory` is outside the leaf's canonical set should not be
   listed on that leaf at all (the consulting firm / cigar shop cases). Check the leaf query in
   `app/categories/leaf_query.py` — apply the same C-1 "allowed set" logic used for chip blanking.
2. **Chip label rendering** (§3.2).
3. **Data corrections** for genuinely misfiled rows (ChaBones is a steakhouse, not cafés-coffee): admin
   review queue for the flagship offenders + the taxonomy rebuild (HAVA_AUDIT_AND_TAXONOMY_REBUILD.md)
   fixes the multi-parent/no-primary structure long-term.

### 3.2 Chip labels drop "&"/accents `[LIVE-BUG]` — one-line fix located
`app/templates/components/sandstone_biz_card.html:29` renders the chip as
`{{ card.subcategory|replace('-',' ')|replace('_',' ')|title }}` — i.e., the SLUG title-cased:
"bars-breweries"→"Bars Breweries", "cafes-coffee"→"Cafes Coffee". The canonical labels
("Bars & Breweries", "Cafés & Coffee") already exist in `app/categories/subcategories.py`.
**Fix:** expose a `subcategory_label(slug)` Jinja filter (or put the label on the card VM) and use it here.
Proof it works: the /lake-havasu/restaurants chip row already renders "Cafés & Coffee" correctly from
`Subcategory.label`.

### 3.3 Broken/garbage addresses `[DATA]` (tooling `[FIXED-BRANCH]`)
Live: Rusty's "2806" (number only); Reflections "Club House - Iron Wolf Golf & Country Club"; **new:**
"Go Lake Havasu Visitor Center" as the address of Black Meadow Landing Diner AND Shugrue's Bridgeview Room
(the *data source* recorded as an address); bare "Lake Havasu City" (Lina Little China); "201 Swanson Ave
Oasis Eateries" (venue glued to address); "333 S. Lake Havasu Ave S" (double directional); "501 english
village Suite 422" (casing). The WS-4 address-quality queue + `scripts/fix_address_quality.py` exist on
the branch — run the flag queue over these patterns (number-only, no-street-token, contains a known
POI/source name, double-directional, lowercase street) after merge. Dry-run → counts → approval.

### 3.4 Default sort floats unrated rows first on /lake-havasu/* `[FIXED-BRANCH — verify]` (new)
Live /lake-havasu/restaurants "Locals' favorites" sort lists ~37 "New / few reviews yet" rows BEFORE
In-N-Out ★4.6 (3,878). The B2 commit ships the WS-2 Bayesian rating prior (C=25, live m) which is exactly
this fix — verify the landing's sort actually uses the prior for no-review rows, merge, deploy, re-check.

### 3.5 Out-of-area rows + formatting `[DECIDE]` + `[LIVE-BUG]`
"Stetson Winery & Event Center … **~155 min away . Parker area**" on the bars leaf (a Kingman-area winery);
"Topock 66 Restaurant … ~45 min away . Parker area". Decide an inclusion radius per surface (e.g., ≤45 min
for leaves, with an explicit "Nearby / day-trip" section if you want to keep them). Separately, fix the
"` . `" separator (space-period-space) in the area suffix — same bug appears in the /lake-havasu filter
bar ("Restaurants . 159 places . x clear").

### 3.6 No-slug tail strip on leaves (new) `[LIVE-BUG]`
After the linked grid, leaves render a strip of UNLINKED name-only cards ("Lake Havasu City" as the only
detail) — including literal duplicates (The Spot ×2 on restaurants, Ghost Mine Saloon ×2 on bars). These
are unslugged/draft rows leaking into the public page. Either exclude slug-less rows from public leaves
or finish materializing them; dedupe regardless.

### 3.7 Verify suspicious names `[DATA verify]`
"Booby Falls Restaurant & Rodeo" (★4.7, 20 reviews, 2100 McCulloch) and "Arizona Rebel Republic Havasu"
(★4.7, 480) — confirm against Google/owner that these are real, correctly named businesses (they look
plausible but odd). Also "Tapusallc" (648 N Lake Havasu Ave) is almost certainly "Tap USA LLC" — fix name.
"DELI LAUNDROMAT" (121 N Lake Havasu Ave) — real combo business or two entities; verify and split/rename.

### 3.8 Missing Open/Closed badge state `[DECIDE]`
Cards with no hours data render with no badge at all (Wolfie's, Monch, Reflections, Tasty Waves,
Piccadilly's, Locos Northside…). Add an explicit quiet "Hours unknown" state (or consistent blank) so the
card layout doesn't read as broken. Spot-check 10 Open/Closed badges against Google at a known local time
(timezone-fix regression check; Siddhartha's Garden showed "Closed" at 6:27 PM Wed, "Open now" at 8:50 AM).

### 3.9 Two competing restaurant surfaces (new, SEO) `[DECIDE]`
`/categories/eat-and-drink/restaurants` ("160 Best Restaurants…", 160 listed) and
`/lake-havasu/restaurants` ("Restaurants in Lake Havasu City", 159 places) are BOTH indexable with
self-canonicals, near-identical intent, different counts. That's keyword cannibalization plus a
trust-smell (159 vs 160). Decide the canonical surface for "{leaf} in Lake Havasu City" queries; point the
other's canonical at it (or noindex it). Also: the landing's "All" chip links `/categories/eat-drink`
(a retired flat route that 301s) — link the canonical department URL directly.

---

## 4. Provider page (`/provider/{slug}`)

### 4.1 JSON-LD bugs `[LIVE-BUG]` — exact lines (provider_profile.html, intact version)
- line 37 `"url": request.url | string` → http behind proxy + echoes query strings. Use
  `canonical_url(request)`/`absolute_url('/provider/' ~ vm.slug)`.
- line 39 `"image": vm.hero_photo_url` → relative `/static/...`. Mirror the og_image logic (line 21) —
  wrap in `absolute_url` when not `http`-prefixed.
- line 54 `"priceRange": None` → emits invalid `"priceRange": null`. Build the dict in Python (view model)
  and omit None keys — cleaner: add `jsonld` to the VM and `{{ vm.jsonld | tojson }}` in the template;
  drop None-valued keys there (also fixes aggregateRating/geo nulls by omission).
- `streetAddress` full-address poisoning — fixed by §1.7 street parsing.
- Enhancement while in there: add `openingHoursSpecification` from `hours_structured` (data's already
  on the page) and `telephone` in E.164.
- After deploy: validate Love's + one restaurant in Google Rich Results test.

### 4.2 Hours table `[LIVE-BUG]`
Live: "Monday 00:00 – Midnight" ×7 + header "Open now · Closes at 11:59 PM" on a 24-hour station.
Template logic at `provider_profile.html:193` maps close 23:59/00:00 → "Midnight" but leaves opens raw
24h. **Fix:** in the hours assembly: if a day's only span is 00:00–23:59/00:00–00:00/00:00–24:00 →
render "Open 24 hours" (and when all 7 days are 24h, the open-status copy should say "Open 24 hours",
not "Closes at 11:59 PM" — fix `is_open_now()`'s derived copy in `app/providers/queries.py`); otherwise
format both ends 12-hour AM/PM ("9:00 AM – 5:00 PM"). The 12-hour formatter already exists
(`_format_class_time` in view_models.py) — reuse.

### 4.3 Review excerpt picker `[LIVE-BUG]` `[DECIDE on policy]`
Love's leads with a towing-threat complaint and the poop-dryer review — `vm.google_review_snippets` is
passed through in raw API order (view_models.py line 326; template takes first 3). **Fix:** select the
3 shown by a quality heuristic — e.g., prefer rating ≥4 for at least 2 slots, length 80–300 chars, most
recent first; never lead with a 1-star when the aggregate is ≥4.0. Keep it honest: don't *hide* criticism
sitewide ("Read all on Google" stays), just don't curate the worst into the first impression. Casey call
on the exact mix.

### 4.4 Breadcrumb label/target mismatch `[LIVE-BUG]`
"Gas Stations" crumb links `/categories/auto-rv-and-marine`. `category_label_for()` returns the specific
label while `_category_url_for()` resolves the department. **Fix:** make the crumb a pair from one source:
if a leaf page exists for the provider's subcategory (e.g. a gas-stations leaf), link label→leaf; else
show the department's LABEL with the department URL. Never label X and link Y.

### 4.5 Route-name inconsistency "US-95" vs "AZ-95" `[DATA]`
Same station: "14875 US-95" on /gas (gas feed data) vs "14875 AZ-95" on the provider page (Google data).
Normalize to AZ-95 (it *is* Arizona SR 95 there) in the gas payload normalizer + address normalizer;
add to the WS-4 mechanical-fix patterns.

### 4.6 "While you're here" relevance `[LIVE-BUG]`
Gas station → 3 Anderson car dealerships. `nearby_providers()` (app/providers/queries.py) matches the
broad `primary_category` ordered by featured/review-count, so big dealers always win within Auto.
**Fix:** prefer same `subcategory` first (gas stations), then same primary; order by distance when
lat/lng available (postal_address has it), then rating; cap featured boost. Keep honest-omission (empty
beats irrelevant).

### 4.7 Claim block copy `[FIXED-TREE? verify]` + `[LIVE-BUG]`
Live shows the bold line + sub "Add more photos and offers." (duplicate work). Copy audit's replacement
sub: "Free — a real person reviews every claim." Tree state of provider_profile.html is currently
truncated (§0.1) — re-apply during restoration. Also the live page renders BOTH the auto-built line and
duplicated claim lines; tree trims the auto-built tail per copy audit §5b.

---

## 5. Gas page (`/gas`)

1. **Missing canonical AND the entire OG block live** — root cause found: `app/api/routes/gas.py:36-37`
   creates its own `Jinja2Templates` without `register_template_filters/globals`, so `canonical_url` is
   undefined and desert_base silently skips the whole SEO block. Same defect in `app/api/routes/micro_ad.py`
   and `app/admin_portal/shared.py` (admin: harmless but fix for consistency). **Fix:** call both registrars
   in those modules (2 lines each); add a regression test that /gas HTML contains `rel="canonical"`.
   `[LIVE-BUG]`
2. Unlinked rows: #5/6 Maverik (2660 Sweetwater) and 76 (2680 Kiowa Blvd N) have no provider link.
   Create/link providers for both (they're real stations) or de-link consistently. `[DATA]`
3. Maverik twins show identical prices across all four grades — could be genuine brand pricing, could be
   one record cloned in the feed. Check `scripts/gas_prices_pull.py` station IDs for the two locations. `[DATA verify]`
4. Staleness phrasing: live "Updated >6h ago (Jun 10, 2026 7:06 AM)". Tree already changes to
   "Updated {timestamp}" with the >Nh form only as fallback `[FIXED-TREE]` — restore after §0.1 (this file
   is one of the truncated ones; the tail also lost the "Prices update once daily. Always confirm at the
   pump." footer — make sure it comes back).
5. Address style in table: "2197 McCulloch" vs "2201 McCulloch Blvd" vs "250 Swanson" — normalize suffixes
   in the gas payload (join with provider addresses where linked). `[DATA]`
6. Breadcrumb "Home · Daily utility" → "Home · Gas" `[FIXED-TREE]` (today.html's twin already fixed:
   tree says "Home · Today").
7. "Mean of every tracked station's regular price" → "Average across all {count} tracked stations"
   `[FIXED-TREE]`.
8. /gas absent from sitemap pages section (`_build_sitemap_pages_xml` static_paths) — add it. `[LIVE-BUG]`
9. /today gas tile says "Cheapest gas — Unavailable · Updated >5h ago" while the strip shows $4.19 and
   /gas renders fine (new): the today-payload gas tile uses a different stale threshold than
   `GAS_STALE_AFTER_HOURS=10`. Align thresholds in `app/conditions/today_payload.py`. `[LIVE-BUG]`

---

## 6. Ad funnel consolidation `[DECIDE]` + mostly small code

Two funnels live: `/sponsor` (4 unpriced packages, `noindex`, sponsors@havasuchat.com) vs
`/portal/advertise` (6 priced products, indexable, claims "the whole rate card" / "No media kit").
A business owner who finds both sees the transparency claim contradicted.
**Recommendation (matches both audits):** make /portal/advertise the single rate card.
1. Change `/sponsor` route (app/home/router.py:1054) to `RedirectResponse("/portal/advertise", 301)`.
2. Repoint `/advertise` 301 (app/main.py:918-923) **directly** to `/portal/advertise` — avoid a chain
   through /sponsor.
3. Home ad placeholders already → /portal/advertise in tree `[FIXED-TREE]`; live still → /sponsor.
4. Retire sponsor_landing.html (or keep as template-dead file removal).
5. The empty-slot duplication on home is fixed in tree: marquee claim stays, "Featured this week" renders
   only when ≥1 real sponsor `[FIXED-TREE]`.
6. Copy decisions while in there: "scarcity-priced" (still in portal_advertise meta line 3 + live /portal
   card) → "limited — one per surface"; "Verified & Enriched Listing" product name + "enriched listing" in
   the founding blurb → keep "enriched" at most once as a brand word `[DECIDE]`.
7. After: click every "Reserve this spot" variant → /portal/reserve?product={founding,category,featured,
   event,gas} renders the right product + the form posts (verification checklist).

---

## 7. Mode pages & map

1. **Orphaned surfaces** `[DECIDE]`: /lake, /night, /family exist, are sold on the rate card
   ("Homepage / Mode Featured $99–199"), but no nav/footer/homepage link reaches them. Either add entry
   points (footer "Explore" column + maybe the home hero area) or pull them from the rate card until launch.
   They're also absent from the sitemap — add when launched.
2. Mode switcher mislabel `[LIVE-BUG]`: in-page pills "Ask | Lake | Night | Family" — "Ask" links `/home`.
   Rename to "Home" (it goes home), `mode_sandstone.html` switcher.
3. Night tiles `[LIVE-BUG]`: "Bars & Lounges" and "Breweries & Wineries" both → `/categories/eat-and-drink`
   unfiltered (`_night_tiles()` in app/home/sandstone.py). Deep-link both to
   `/categories/eat-and-drink/bars-and-breweries` (the leaf exists — crawled it). Live Music/Happy Hours/
   Late Kitchens/Get Home Safe → /chat queries are deliberate; keep.
4. Mode meta descriptions are the generic homepage one — give each mode a one-liner. `[LIVE-BUG]`
5. Map third taxonomy `[DECIDE/workstream]`: /map's Categories list (12 hardcoded slugs in
   `serve_map_view()`, app/home/router.py — "Outdoors, Parks & Trails", "Auto, RV & Fuel"…) matches neither
   the 15 directory departments nor the nav. Fold into the taxonomy rebuild: derive map scopes from the
   same canonical source as nav/mega/categories index. Quick interim win: rename labels to match the
   directory's department names.
6. Map title uses `&mdash;` entity while every other title uses the literal — normalize (`map_c.html:8`). Cosmetic.
7. Stray "Toggle map" text seen in the live audit: tree has the button `hidden` (`map_c.html:57`) — likely
   already fixed pending deploy; verify post-deploy with a rendered-browser pass.

---

## 8. SEO / meta / infrastructure

1. **www host** `[OPS]`: original audit saw `www.askhava.com` serving the full site on www with 200s.
   Today's fetch of www appears to land on `https://askhava.com/home` — possibly already fixed at DNS, or
   the fetch tool followed silently. Verify with `curl -I https://www.askhava.com/` ; if it 200s or stays
   on www, either fix DNS/Railway or add `"www.askhava.com"` to `_LEGACY_HOSTS` in app/main.py (one line —
   the middleware already 301s legacy hosts; requires Railway to route the www host to the app).
2. Meta descriptions `[LIVE-BUG / FIXED-TREE mix]`: /privacy + /terms reuse the homepage description
   (pass a `meta_description` into privacy_doc context, e.g. "How Hava handles your data — what we store,
   who processes it, and your choices." / terms one-liner). /events-ui fixed in tree. /login has one in
   tree. /contribute has none (add when rebuilding that page §10.4). Mode pages — §7.4.
   /lake-havasu/* landings reuse the homepage description (new) — generate per-landing from the
   subcategory one-liner.
3. Titles `[LIVE-BUG]`: "Privacy — Hava" / "Terms — Hava" hardcoded in app/main.py:951,956 →
   "… — Ask Hava". Contribute title fixed in tree ("Add to Hava — Ask Hava") ✓.
4. Canonicals: /gas + missing-OG root cause §5.1; /contribute has no canonical (hand-built head — §10.4).
5. JSON-LD coverage `[LIVE-BUG]`: add Organization+WebSite (with SearchAction → /chat?q=) on /home;
   Event schema §2.7; LocalBusiness fixes §4.1; BreadcrumbList on leaf/provider pages is a cheap add.
6. No `twitter:card` anywhere: add `summary_large_image` + title/description/image to desert_base head
   (mirrors og) — one edit covers the site.
7. Per-page OG images: acceptable shared hero for now; leaf pages have curated photos
   (`curated_category_photos.json`) — wire leaf og:image to the category photo. Low effort, nice lift.
8. Security headers: HSTS/Referrer-Policy/Permissions-Policy/no-cache exist on main; live absence =
   deploy issue (§0.2) + HSTS needs §0.4. CSP remains deliberately deferred — keep tracked.
9. robots.txt: currently `Allow: /` only. Optionally `Disallow: /admin`, `/api/`, `/account`, `/logout`
   (auth-gated anyway; hygiene). Low priority.
10. Sitemap gaps: add `/gas` (§5.8); add mode pages when launched (§7.1); `/search` intentionally out, fine.
    sitemap-providers will shrink as dup merges land (B1 301s drop losers via is_active).
11. Canonical strategy `/` vs `/home` `[DECIDE]`: root 301s to /home and canonicals point at /home.
    Serving the homepage at `/` is cleaner long-term; decide once, low priority. (sitemap already
    deliberately lists /home only.)
12. `/categories/eat-drink` style retired flat routes still linked from the /lake-havasu filter bar
    ("All" chip) — link canonical department URLs directly (§3.9).

---

## 9. Conditions strip & /today (several NEW findings)

1. **Lake level shows "48.9 ft"** (new) `[LIVE-BUG?]`: Lake Havasu pool elevation is ~448–449 ft; the
   /today tile shows "48.9 ft / Lake gauge / USGS 09427500". Likely gauge *stage height* (datum-relative)
   rendered where locals expect elevation (the old prototype hardcoded 448.7 ft). Fix: use elevation
   (stage + gauge datum, or the lake-elevation parameter/site) or relabel honestly ("Gauge height").
   Verify against USGS site data for 09427500 before changing math.
2. **UV value suspect** (new evidence) `[LIVE-BUG?]`: live strips showed UV 0.5 (evening per first audit),
   then UV 10 at ~8:50 AM, UV 2, UV 0.1 across cached vintages. After the cache fix (§0.2), if oddities
   persist the likely cause is an hour-lookup using UTC against a local-hour table (8:50 AM MST = 15:50
   UTC; June UV at ~3:50 PM local ≈ 8–10 — exactly what was shown). Audit `app/conditions/uv.py` /
   `epa_uv.py` / `openuv.py` hour selection for tz correctness; add a test pinning "morning hour → morning
   UV". Then sanity-check ~solar-noon shows ~10–11 in June.
3. AQI "(O3)" `[LIVE-BUG]`: `app/conditions/view_model.py:137` uses the pollutant parameter as the chip
   detail. Replace with EPA category word: "AQI 40 · Good" (map 0-50 Good / 51-100 Moderate / …); keep the
   pollutant in the title-attr detail if wanted. Same change for the /today air-quality tile (secondary
   currently "O3").
4. /today gas tile threshold mismatch — §5.9.
5. /today header "as of 7:06 PM" contradicting tiles' "Updated 5 min ago" (new): re-check after the cache
   fix; if it persists, audit `local_time_label` AM/PM formatting in `app/api/routes/today.py`.
6. Water temp "Unavailable" on /today while About promises "today's lake level and water temperature"
   `[DECIDE]`: either fix the water-temp source (usgs_water_temp / rise_water_temp) or soften the About
   sentence (link it to /today: "today's <a href=/today>conditions</a> — lake level, wind, air quality…").
7. /today breadcrumb "Home · Daily utility" → "Home · Today" `[FIXED-TREE]` ✓ deploy.

---

## 10. Copy & voice (state of the copy-audit implementation + what remains)

Much of COPY_AUDIT_2026-06-10.md is ALREADY implemented in the working tree (uncommitted) — it must
survive the §0.1 restoration. Verified present in tree before truncation:
- Hero B default + eyebrow→date + "Your local concierge" on askbar (home_sandstone.html) ✓ (+ §0.3 env)
- "The month *at a glance*" retitle ✓ · single empty-ad rule ✓ · home cards → /portal/advertise ✓
- Week-strip legend "Special event" naming ✓
- login.html / login_check_email.html contractions + 15-minute line ✓
- not_found.html "Ask Hava where it went →" CTA ✓
- about.html "Built here, for the people…" ✓
- today.html breadcrumb ✓ · gas breadcrumb/avg/staleness copy ✓ (in the truncated file — re-apply!)
- contribute title/eyebrow "Add to Hava" ✓ (rest of that page: below)
- portal_claim "tap "Claim this listing"" stray-space fix → proper &ldquo;…&rdquo; ✓
- portal_index + portal_advertise comments show the scarcity-priced / enriched sweep was started —
  but "scarcity-priced" is still in portal_advertise.html:3 meta `[REMAINS]`
- leaf_copy.py jargon sweep done in tree (0 hits; main still has 18) ✓
- categories_index meta rewritten ✓

Still open:
1. Jargon sweep — fully located, fully fixed in tree, pending deploy: dept intro
   (`category_department.html:22`, tree now reads "Every list comes straight from the local directory,
   ranked by real public reviews — more reviews, more weight…" ✓); the live leaf-FAQ line "The list is
   server-rendered from our local directory" comes from `leaf_copy.py:33` AND `trades.py:87` on main —
   both swept in tree (0 hits) ✓. FAQ "How are these ranked?" answer's "volume-weighted rating" is fine
   in context (it explains itself) — keep or simplify, Casey call.
2. /contribute page rebuild `[DECIDE]`: it's a hand-built f-string page (contribute.py) on a *different
   design system* (Inter/Fraunces fonts, own CSS, no site footer, "Hava" wordmark), no canonical, no meta
   description, **no Plausible analytics include** (contribute traffic is invisible today), and internally
   mixed voice ("I'll review" vs "We review most submissions" on the same page). Recommend migrating it to
   a Jinja template extending desert_base (keeps the focused-form layout via a slim variant), which fixes
   head/SEO/analytics/footer in one move. Until then: the `--` double-hyphen ("submission -- never for
   marketing") → em dash; pick one voice (Hava-first-person per the codified rule below).
3. Codify the voice rule in WORKING_AGREEMENT.md or a new docs/VOICE.md: **Hava says "I" on product
   surfaces (chat, contribute); the company says "we" on about/help/contact/legal/business pages.** ✸ Add
   the keep-list from the copy audit ("don't touch" lines) so future passes don't regress them.
4. Events group label "Events" → "Around town" §2.8 `[DECIDE]`.
5. Chat composer "Photo" bare text button (chat.html:55): icon + label to match polish bar; confirm the
   photo-upload path end-to-end in a browser pass.
6. About page lake-level/water-temp promise §9.6.
7. "Hours unknown" badge state §3.8 (copy: "Hours unknown — call ahead").

---

## 11. Verification checklist (for the implementation PRs; run after each batch deploys)

Repo/tree health:
- [ ] Other session stopped; `.git/index.lock` removed; `git status` clean of surprises
- [ ] NUL bytes: `grep -rlP '\x00'` over tracked text files returns nothing
- [ ] All templates parse: quick script env.parse() over app/templates/**
- [ ] `python -m pytest -q` green and `ruff check .` clean before every commit (CLAUDE.md gate)

Live-site, after deploy + cache purge:
- [ ] `curl -I https://askhava.com/home` → Referrer-Policy, Permissions-Policy, Cache-Control: no-cache,
      Strict-Transport-Security present (HSTS proves §0.4 worked)
- [ ] `curl -I https://www.askhava.com/` → 301 to https://askhava.com/… (one hop)
- [ ] `curl -I https://havasu-chat-production.up.railway.app/` → 301 to askhava.com
- [ ] /gas footer email correct; /gas head has canonical + og:*; conditions strip consistent across pages
- [ ] grep live HTML of /sponsor (or its 301), /terms for `havasuchat` → zero
- [ ] /privacy + /terms: read every bullet/paragraph; no AI-draft comment in page source
- [ ] /favicon.ico 200; tab icon renders; apple-touch-icon on iOS save
- [ ] advertise-page cactus screenshot (mobile + desktop)
- [ ] /events-ui: Board of Adjustment under Community; no doubled Aquatic/Pilates rows; no time-in-title;
      no /events-ui self-links; home day counts == events-ui group sums
- [ ] Love's: street-only address line; "Open 24 hours"; review excerpts pass the quality rule;
      breadcrumb label matches target; JSON-LD passes Rich Results test (https url, absolute image,
      no null priceRange)
- [ ] Restaurants + bars leaves: chips show "&"/accents; no off-category chips; dup clusters merged
      (Broken Yolk, Denny's, Niko's, Hangar 24, Rosati's, Shugrue's, Sloane's, Dos Amigos, Filiberto's,
      Montana's, Turtle Grille, The Spot, Bad Miguel's, Reflections, Lin's/Lina, McKee's, Ghost Mine ×2)
- [ ] /lake-havasu/restaurants default sort: rated institutions first (prior live)
- [ ] Every "Reserve this spot" product → form renders right product; submit works
- [ ] Crawl sitemap-providers.xml: 0 dup (name,address) pairs, 0 404s; sitemap-pages includes /gas
- [ ] Spot-check 10 Open/Closed badges vs Google at a known local time
- [ ] All 15 department pages + each leaf: chip/intro/FAQ jargon sweep rendered correctly
- [ ] Lighthouse (perf/a11y/SEO) on home/category/provider/events — capture the baseline this time
- [ ] Rendered-pixel pass on mobile widths + Night theme (this audit was markup-level; spacing/overflow/
      contrast/dark-mode still unverified) — includes "Toggle map" gone, loading micro-ad surface,
      chat streaming, calendar interactions, photo upload

Known-unverifiable in this pass (carry over): JS behaviors (rotating placeholder, calendar, chat stream,
map pins), image quality/cropping, Core Web Vitals.

---

## 12. Suggested PR batching (respecting CLAUDE.md gates — every PR: tests green, ruff clean, no direct main pushes)

0. **PR-0 Tree rescue** (§0.1): NUL strip + template-tail restoration + parse test. Nothing else mixes in.
1. **PR-1 Ops bundle** `[OPS, no PR]`: Railway deploy verify/redeploy + cache purge + hero env + mailbox
   decision. (Casey actions; 30 min.)
2. **PR-2 Quick trust fixes**: tos.md domain+date, event_ingest fallback URL, privacy renderer fix (+test),
   strip AI comment, cactus SVG, favicon set, privacy/terms titles+meta, gas.py+micro_ad.py template
   globals (+canonical test), Procfile --proxy-headers, twitter:card in base, sitemap +/gas.
   Small, reviewable, zero product decisions.
3. **PR-3 Events quality**: word-boundary tiers + civic hints (+tests), drop_event_duplicates fuzzy
   matching, schedule-import dedupe, clean_event_title at ingest (+fixtures), one counting rule (+test),
   non-link class rows, month-pill default type, Event JSON-LD. `[DATA]` title backfill + schedule-row
   cleanup ride separately with dry-runs.
4. **PR-4 Provider page**: JSON-LD via VM dict (https url, absolute image, omit-None, hours spec),
   Open-24-hours + 12-hour formatting, review-excerpt heuristic, breadcrumb pairing, nearby_providers
   subcategory/distance preference, claim-block copy.
5. **PR-5 Directory surface**: chip label filter, leaf listing subcategory filter, no-slug tail exclusion,
   "Hours unknown" state, " . " separator fix, /lake-havasu canonical decision implementation.
6. **PR-6 Funnel + modes**: /sponsor 301 + /advertise repoint + template retirement; mode switcher label,
   night tile deep-links, mode meta; map label alignment (full taxonomy unification stays in the rebuild
   workstream).
7. **Merge B1/B2/WS-4 branch** (already on its own PR path per docs/PR_TRACK_B_B1_B2_2026-06-10.md), then
   the `[DATA]` campaigns: dup-cluster merges, address mechanical fixes, havasuchat event_url backfill,
   title backfill — each dry-run → counts → Casey approval → apply.
8. **Copy polish PR** last (lowest risk, easiest review), incl. contribute-page migration if approved.

---

## 12b. IMPLEMENTED THIS SESSION (Cowork, ~9:30 AM) — uncommitted, Windows-side edits only

Done in the working tree by THIS session (no git ops, no mount-shell writes — other agents: these
files are claimed, please don't re-edit without checking):

| Fix | Files | Status |
|---|---|---|
| §1.3 classifier: word-boundary hint matching (+plural/gerund tails, "fest" suffix exception) + civic→Community tier | `app/home/sandstone.py` (`_CIVIC_HINTS`, `_compile_hints`, `_event_tier`, `_event_css_type`) | DONE — logic replica-tested (24 cases) |
| §2.1A event-vs-schedule dedup: normalized token-subset match + ±30-min window; callers pass (title, date, start_time); legacy 2-tuple keys still accepted | `app/events/class_occurrences.py`, `app/home/events_views.py` (×2 sites), `app/home/sandstone.py` (week_strip + calendar_month) | DONE — replica-tested incl. live aquatic pairs |
| §2.1B schedule-twin collapse (Pilates double-capture) at read time | `app/events/class_occurrences.py` `_drop_schedule_twins`, wired into `class_occurrences_in_window` | DONE (data cleanup of Schedule rows still pending) |
| §2.4 slugless class rows: no more `/events-ui` self-link; non-link row rendering | `app/events/class_occurrences.py` (`url` → ""), `app/templates/events_sandstone.html` (row branch) | DONE |
| §5.1 /gas missing canonical+OG: register shared template filters/globals | `app/api/routes/gas.py`, `app/api/routes/micro_ad.py` | DONE |
| §0.4 proxy scheme: `--proxy-headers --forwarded-allow-ips="*"` | `Procfile`, `nixpacks.toml` | DONE — fixes HSTS emission + future request.url uses; provider JSON-LD template fix (§4.1) still separate |
| §1.1 event-ingest fallback URL havasuchat→askhava | `app/contrib/event_ingest.py` (both sites) | DONE (DB backfill of existing rows still pending `[DATA]`) |
| §9.3 AQI chip "(O3)" → "AQI 40 · Good" (+pollutant moved to hover detail) | `app/conditions/view_model.py` (`_aqi_category`) | DONE (the /today tile's "O3" secondary is in `today_payload` — not touched) |
| §13.6 search page: canonical subtype labels, street-only address, digit `tel:`, noindex on results | `app/search/routes.py` (`_humanize_subtype`), `app/templates/search.html` | DONE |
| New tests | `tests/test_event_tier_classifier.py`, `tests/test_class_event_dedup.py` | NEW FILES |

Known limitation left documented: "Arthritis Class Vince" vs "Arthritis Water Class" token sets are not
subset-related — that one pair still doubles until the Schedule-side data cleanup.

Verification status: logic validated via standalone replicas (sandbox /tmp, off-mount); edited regions
re-read Windows-side and intact. **The sandbox mount serves stale/truncated views of these files — do
NOT trust mount-side py_compile/pytest.** Authoritative gate per WORKING_AGREEMENT: Casey runs
`.venv\Scripts\python.exe -m pytest -q` + `ruff check .` Windows-side before commit.

### Batch 2 (next morning, after the copy track merged — files freed up)

| Fix | Files | Status |
|---|---|---|
| §1.2 privacy renderer: wrapped bullets join one `<li>`; HTML comments no longer ship to page source (+tests) | `app/main.py` `_render_doc_markdown_to_html`, `tests/test_legal_doc_rendering.py` (new) | DONE — replica-run against real privacy.md: 19 clean bullets |
| §13.4 `_event_is_past`: 3h grace for end-time-less events (9:00 AM meeting no longer "passed" at 9:07) | `app/main.py` + `tests/test_event_permalink_context.py` updated to pin new contract | DONE |
| §8.3 legal titles "— Ask Hava" + per-page meta descriptions for /privacy /terms | `app/main.py`, `app/templates/privacy_doc.html` | DONE |
| §5.8 sitemap pages section + `/gas` | `app/main.py` | DONE |
| §1.6 favicon (SVG) + manifest + theme-color; §8.6 twitter:card set | `app/templates/desert_base.html`, `app/static/img/favicon.svg` (new), `app/static/manifest.webmanifest` (new) | DONE — **binary residue:** real `/favicon.ico` + PNG apple-touch icons still need image tooling |
| §1.5 cactus arms point up | `app/templates/portal_advertise.html` | DONE (verified coords; screenshot after deploy) |
| §7.3 night tiles → bars-and-breweries leaf; §7.2 switcher "Ask"→"Home"; §7.4 mode meta = blurb | `app/home/sandstone.py`, `app/templates/mode_sandstone.html` | DONE |
| §2.8 events group label → "Around town" | `app/home/events_views.py` | DONE |
| §5.9 /today gas tile uses GAS_STALE_AFTER_HOURS | `app/conditions/today_payload.py` | DONE |
| §2.7 Event JSON-LD on /events/{id} (dict built route-side, AZ -07:00, None keys omitted) | `app/main.py`, `app/templates/event_permalink.html` | DONE — validate in Rich Results after deploy |
| §13.1 reserve-form categories from canonical departments (fallback to legacy list on DB hiccup; POST validates + snapshots from rendered options) | `app/portal/router.py` | DONE |
| §13.8 collection "Add it to Hava"; §13.7 "Bundled categories" slug leak removed; §7.6 map title literal — | `collection_landing.html`, `themed_group_landing.html`, `map_c.html` | DONE |

Still not touched / remaining for other lanes: provider JSON-LD + hours/review/breadcrumb/nearby (§4 —
Track B owns provider files), `[DATA]` campaigns (dup merges, address fixes, title backfills, Schedule-row
cleanup, havasuchat event_url backfill), taxonomy rebuild (map scopes §7.5, two-restaurant-surfaces §3.9,
leaf slug `caf-s-and-coffee` §13.3 — slug lives in DB taxonomy, needs migration+301), favicon binary
assets, UV hour-source audit §9.2 (re-check after today's deploys), CSP (deliberately deferred).

---

## 13. ADDENDUM — sweep #2 (same day, ~9:00–9:20 AM MST)

Second full pass over pages not covered the first time: categories index, eat-and-drink department,
events week view, an event permalink, /search, /about, /login, /portal/claim, /portal/reserve (category
variant), /lake, a collection page, /group/things-to-do-group, /lake-havasu/restaurants?page=2,
/events.ics, plus a full route inventory and dead-link hunt. Tree status re-checked: `.git/index.lock`
**still present**, the 4 truncated templates **still broken** — §0.1 unchanged.

### 13.1 Reserve form sells categories that don't exist `[LIVE-BUG, revenue]` — biggest new find
`/portal/reserve?product=category` → the "Which category?" dropdown lists the **map taxonomy**
(13 options: "Auto, RV & Fuel", "Classes, Sports & Recreation", "Outdoors, Parks & Trails",
"Public & Civic Resources", "Shopping, Grocery & Essentials", even "Events") — NOT the 15 directory
departments the Category Sponsorship product actually pins a sponsor onto. Missing entirely:
Beauty & Personal Care, Fitness & Wellness, Family & Education, Things to Do & Attractions,
Community & Civic. A paying advertiser cannot select the page they want, and "Events" is offered as a
sponsorable *category* though it's sold separately as Event Boost.
**Fix:** source the dropdown from the canonical department list (same source as nav/mega), in
`app/portal/products.py` / the reserve template; map any existing reservations forward. Goes in PR-6.
The product card + form render correctly per product otherwise (`?product=category` verified ✓).

### 13.2 Categories index (/categories) `[LIVE-BUG]`
- **Double-escaped "peek" names:** renders literally as "Sweet Treats &amp;amp; More" and
  "Christine&amp;#39;s Fine Art LLC" — peek business names are HTML-escaped twice
  (`categories_index.html` peek rendering escapes already-escaped strings; store/emit raw + escape once).
- Peek pairing data: "Havasu Watercraft Rental" is the peek for **Professional & Financial** (misfiled
  provider showing on the index); Family & Education + Community & Civic cards have no peek at all
  (inconsistent card states).
- Eyebrow timestamp "Wednesday, June 10 · 5:20 PM" served at ~9:05 AM — another §0.2 cache vintage.

### 13.3 Cafés leaf slug lost its accent `[LIVE-BUG]`
Eat & Drink department links the leaf as `/categories/eat-and-drink/caf-s-and-coffee` — the slugifier
dropped "é" instead of transliterating ("cafes-and-coffee"). `app/utils/slug.py` is modified in the
working tree (possibly already addressed — verify); the leaf slug looks persisted in taxonomy data, so
fixing requires: transliterating slugify (é→e), data migration of the stored slug, and a 301 from
`caf-s-and-coffee`. Check for other accent/apostrophe victims in stored slugs while at it.

### 13.4 "This event has passed" fires the minute an event starts `[LIVE-BUG]`
The Board of Adjustment permalink showed the "passed" banner at 9:07 AM for a 9:00 AM meeting —
`_event_is_past()` (app/main.py) treats `end_time or start_time` as the cutoff, so any event without an
end time is "past" at start+1 min. **Fix:** when `end_time` is None, use `start_time + grace`
(2–3 h) or end-of-day. Also on that page: the Directions button targets bare "Lake Havasu City"
(useless map pin) — suppress Directions when `location_name` is just the city.
Bonus confirmation: the event's own tags are `civic, government, meeting` — the data to classify it
correctly already exists; only the §1.3 hint logic stands in the way.

### 13.5 Counting-rule divergence is user-visible on two live surfaces at once
/events-ui?view=week (live) shows "Today: 4 events · 1 music · 48 classes" while the home strip (live)
shows "12 events · 41 classes" for the same day (totals both 53; Thu/Fri rows diverge the same way).
No new fix — this is §2.5 — but it upgrades the priority: the disagreement is two clicks apart.

### 13.6 /search page `[LIVE-BUG]`
- Category labels are raw Google type tokens: "mexican_restaurant", "fast_food_restaurant",
  "bar_and_grill", "taco_restaurant", "catering_service", plus inconsistent "restaurant"/"restaurants".
  Map tokens through the canonical label system (or at minimum `replace('_',' ')|title`).
- Addresses render full Google format incl. ", USA" — reuse the §1.7 street-line formatting.
- `tel:` hrefs contain formatting: `tel:(928) 540-5158` — emit digits only (provider pages already do).
- The Dos Amigos dup pair surfaces here with **identical phone numbers** → add phone equality as a
  dedup-cluster key in the §1.4 pass.
- Hygiene: consider `noindex` on /search results (it's already excluded from the sitemap; canonical
  strips ?q ✓).

### 13.7 /group/{slug} themed-group family `[DECIDE]` + data noise
`/group/things-to-do-group` renders a full surface that **nothing links to** (no template references
found — orphan family, like the mode pages). On it:
- Internal slugs printed to users: "Bundled categories: events, outdoors-parks-trails,
  classes-sports-recreation" (`themed_group_landing.html`) — remove or humanize.
- All 30 cards say "Hours unknown" — for parks/trails/golf the label is noise; suppress it for outdoor
  categories (or only show when hours are *expected*).
- Subtype mislabels: Win Win Bingo Casino → "Parks & Playgrounds"; Islander RV Resort → "RV Sales &
  Service" (it's a campground); Rotary Community Park → "Boat & Watercraft Rentals"; three golf courses →
  "Parks & Playgrounds".
- More dup clusters: "Lake Havasu Golf Club - East Course" / "Lake Havasu Golf Club East" (+ West twin);
  "Bird Watching" AND "Bird Watching in the Havasu National Wildlife Refuge" exist as provider listings
  (activities stored as businesses — fold into the refuge entity or a guide page).
- `/group/eat-drink-group` returned an empty body twice while things-to-do renders — verify status code
  (500 vs tool artifact); slug is valid per `THEMED_GROUPS`.
- Decide: link the group pages somewhere (map "Collections" tabs are the natural place) or retire them.

### 13.8 Smaller items
- `/events.ics` (calendar feed) works and contains **zero** havasuchat URLs ✓ (spot-checked by grep, not
  a full read) — but the §2.2/2.3 junk titles flow into subscribers' calendars verbatim
  ("SUMMARY:Fit & Flex (155) Stephanie") — title cleanup pays off twice. Feed appears unlinked from any
  page — consider an "Add to your calendar" link on /events-ui once titles are clean.
- Collection page (`/collection/dog-friendly-patios`) is in good shape; one copy nit:
  "Add it to the **catalog**" (`collection_landing.html:54`) → "Add it to Hava".
- `/district/{slug}` URLs are built in `view_models.py` (district_chip_*) but **no such route exists**;
  currently unrendered by the template so not a live 404 — either add the route or drop the dead fields.
- Route inventory confirms `/claim/{slug}` (auth/routes.py:376) and `/upgrade/{slug}` exist — the
  provider-page Claim CTA is NOT a dead link ✓.
- `/lake-havasu/restaurants?page=2` canonical correctly preserves `?page=2` ✓ (P1.4 working); page-2 title
  "— Page 2 —" ✓. Meta description still the generic homepage one (covered in §8.2).
- Page 2 also provided the cleanest §0.2 evidence: an evening-cached render served at 9 AM shows
  breakfast spots (Peggy's Sunrise, Broken Yolk) "Closed" and Pizza Hut "Open now" — keep as the
  post-deploy regression test case.
- `/category/restaurants` (the D6 Tier-1 landing family) returns an empty body — inventory which
  `/category/{slug}` slugs are actually live, and fold the decision into §3.9 (two-surfaces question).
- `/lake` mode page: same known mode items (generic meta, orphaned); tiles OK otherwise.
- `/portal/claim` fine; "enriched profile" wording → §6.6 decision. Reserve-form canonical strips
  `?product` (all variants canonicalize to /portal/reserve) — acceptable.
- /about + /login live still serve the pre-fix copy — §10 items, deploy-gated ✓ (no new work).

### 13.9 Addendum → PR mapping
PR-2 (+§13.2 double-escape, §13.3 slug+301, §13.4 passed-banner+directions, §13.6 search labels/addresses/tel),
PR-3 (+§13.5 evidence, §13.8 ICS note), PR-5 (+§13.7 group-page label suppression + slug leak, §13.8
collection copy, district dead-fields), PR-6 (+**§13.1 reserve dropdown — do not ship the funnel
consolidation without it**), `[DATA]` campaigns (+golf-club trio, Bird Watching pseudo-rows, Win Win
Bingo / Islander RV / Rotary Park subtype fixes, phone-equality dedup key).
