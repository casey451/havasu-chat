# Hava — UI Critique & Redesign Spec

**Audit target:** `https://havasu-chat-production.up.railway.app/home`
**Source audited:** `app/templates/home.html`, `app/static/styles/home.css`, `app/static/styles/chat.css`, `app/home/queries.py`
**Date:** 2026-05-08
**Premise from owner:** "Nothing in it needs to stay. Colors, layout and functionality can all change."

This document has two parts. **Part A** is a critique covering everything I'd raise as a UI lead reviewing the live page. **Part B** is the actual redesign direction: tokens, components, screens, and a prioritised, file-level Cursor task list. The Cursor agent should treat Part B as the build spec; Part A explains the *why* so judgement calls in implementation align with intent.

---

## Part A — Critique

### A1. The headline problem: the page reads like a database, not a product

The single most damaging issue is that backend data is leaking into the surface text. Once you see it, it's everywhere:

- The category strip shows `health_medical`, `food_drink`, `home_services`, `lake_recreation`, `professional_services`, `beauty_personal_care`, `auto`, `religion_community`, `fitness_sports`. Those are raw enum slugs from `Provider.category`. A screen reader literally says "find a underscore health underscore medical." A human reads it as "this product isn't finished."
- Every event card under *Tonight*, *This week* and *New on Hava* contains a templated string of the form: *"Lap Swim on 2026-05-08 at 5:00 AM at the Lake Havasu City Aquatic Center. See full schedule and current pricing at https://www.lhcaz.gov/parks-recreation/open-swim-schedule."* That is the `Event.description` column being sliced to 180 chars and printed verbatim — ISO date, raw URL, repeating boilerplate. Six cards on the page show near-identical text.
- The Farmers Market card is worse: it's a CSV-style dump — *"Date: May 09, 2026\nTime: 12:00 – 12:00\n\n\nVenue: 2144 McCulloch Blvd NLake Havasu City, AZ 86403\nOrganizer: Havasu Together\nCategories: Farmer's Market"*. The address is missing a space between "N" and "Lake", the time range shows start = end, and the labels themselves are visible.
- "Open · until 6" / "Open · Hours on profile" status pills are placeholder strings hard-coded in `_hours_status`. Real hours are not yet wired.
- All three "Spotlight" phone numbers are `(928) 555-01XX`, which is the North American Numbering Plan reserved range — also placeholder.

**Why it matters more than aesthetics.** A Lake Havasu local who lands here and reads "find a religion_community" will close the tab. The brand promise — *"the AI local who has walked the town"* — collapses against the visual evidence of unfinished plumbing. No amount of typography fixes this; the content layer has to be cleaned first.

### A2. The "Tonight" row shows 5 AM, 8 AM, and 8:15 AM events

`tonight()` in `app/home/queries.py` filters `Event.date == today`. That's "today's events," not "tonight's events." The result is a *Tonight* row that shows lap swim at 5 AM at the Aquatic Center as the hero card. The label promises evening; the data shows pre-dawn. Either the label or the query needs to change.

It's also the same venue three times in a row. A page section that's meant to summarise *Tonight in Havasu* is, today, three rows of pool schedules.

### A3. Photography is missing where it matters

The hero, the editorial *Hava's Read*, and the cinematic ambition of the type system are doing real work. Then every event card lands on a flat tan gradient placeholder because `image_url` is hard-coded `None` (`_provider_image_url` returns `None`; events have no image surface yet). The three cards *with* images — the paid Spotlight businesses — visually dominate the page entirely. The result is that paid placement is the only thing that looks finished. That's the inverse of what you want.

### A4. Visual variety is too thin

The page has one accent (teal `#0e6e7c`), one warm secondary (terracotta `#b8623d`, used on exactly one element), and a "live coral" `#e8654a` that never actually appears on the page. The category icons are ten identical filled circles. The card variants — `card-feature`, `card-side`, `card-tall`, `card-biz` — render almost identically: same radius, same shadow, same tan gradient, same `→`, same uppercase footer. Scanning the page is hard because nothing tells your eye where to land.

The hero's italic "*Havasu*" in Fraunces variable optical-size 144 is the only typographic moment that has personality, and it appears once.

### A5. Information architecture is chat-only

Every chip, category tile, "see all", spotlight card, and even the footer "List your business" link routes to `/chat?q=…`. There is no browse mode. If I want to scroll a list of plumbers, I have to type into a chat box and read prose answers. That is fine as Hava's *primary* affordance, but losing the browse-mode escape hatch entirely makes the page feel like a single-button kiosk. Categories should also support "tap to filter the page" or "tap to open a list view," not just "tap to start a chat."

### A6. Time-of-day and locality cues are wasted

The dateline (`Lake Havasu City · Friday, May 8`) is the most place-specific thing on the page — and it's hidden on mobile (`.topbar-meta .dateline { display: none; }` until ≥720 px). The page knows it's Friday morning, but the *Tonight* header doesn't acknowledge "you'll need a plan in 9 hours," the hero pulse animates in terracotta with no semantics behind it, and the Hava's-read blockquote is a canned "Tonight's looking calm and clear" that reads identically every refresh. Lake Havasu is a real place with a *thing* — the channel, the bridge, the lake itself, the sunset over Pittsburg Point. None of that visual identity is on the page.

### A7. Hierarchy between paid and editorial is muddy

*Local pros · Spotlight · paid placement* is the only paid surface. Good — disclosure is present. But the Spotlight cards look better than every event card on the page (because they have images), so the hierarchy reads as *"the businesses who paid us are more important than the events."* That's the opposite of what an editorially trustworthy local guide should communicate. Editorial picks need to be the visual stars, with paid placement clearly secondary even though commercially essential.

### A8. The card grid is monotone

Three sections (`This week`, `New on Hava`, `Tonight` side cards) all use a 3-column grid of identical-looking cards, each ending in `→`. Nine `→` arrows in the same column position. No magazine pacing — no wide image, no inline list, no map module, no testimonial, nothing. The page wants to be editorial; the grid is a feed.

### A9. Empty states betray the work

- The sponsor slot fallback is *"This slot is open"* — honest but a deflating bottom-page CTA after a row of paid spotlight cards above it.
- *Hava's Read on Tonight* is a static blockquote that re-renders the same phrase on every load.
- The category strip uses snake-case enums when the database is empty of real categories; the *good* fallback list (`_default_categories` in `queries.py`: "Plumbers, Electricians, HVAC, Pool service…") is only used when there are zero providers. The buggy live path runs whenever even one provider exists.

### A10. Smaller stuff (real but lower priority)

- Footer has duplicate links: *List your business* and *Sponsor a slot* both point to `/sponsor`.
- `<div class="chips" role="list">` with `<a role="listitem">` — `<a>` is not a valid `listitem` child without role contortions; use `<ul>`/`<li>` and remove ARIA.
- `--ink-3` `#6e6e67` on `--bg` `#f7f5ef` is right at WCAG AA (about 4.6:1) — fine for meta, but the comment in CSS says "never use for body copy" yet it ends up doing visual heavy lifting in card meta and footer text.
- The composer is a `GET` form to `/chat`. Pressing Enter does a full page navigation. There's no client-side enhancement, no "thinking…" state, no recent searches, no history.
- No `focus-visible` styles defined on cards or chips. Keyboard users get the browser default.
- Google Fonts is loaded with two faces and a wide variable axis (`9..144`) — the page can render before fonts load and FOUT/FOIT depending on browser.
- The hero composer's `<button class="send">` swaps from black background to teal on hover — a small but striking colour swap that has no equivalent elsewhere; it reads as a one-off rather than a system rule.
- The Unsplash images on Spotlight cards have no `width`/`height` — they cause layout shift on first paint.
- The Lake Havasu City Aquatic Center event blurbs each contain the URL `https://www.lhcaz.gov/parks-recreation/open-swim-schedule` truncated mid-character (the 180-char slice cuts to "schedul" in some cards).

---

## Part B — Redesign direction

The redesign should keep one thing: the brand promise. *Hava is the AI local of Lake Havasu City.* Everything else — the palette, layout, type pairing, components, and even the IA — is in scope.

### B1. Concept

**Editorial almanac, not a search bar.** Lean into the persona brief: Hava has *walked the town*. The home page should feel like a folded-paper local guide that re-prints daily — magazine pacing, a real sense of place, and an AI prompt that's a *secondary* affordance, not the centerpiece. The chat is *one* way to ask Hava; the page itself should be readable like a Friday morning newspaper.

Three product moves drive the redesign:

1. **Time of day is the spine.** The page changes header, accent gradient, and copy for dawn / morning / midday / sunset / night. *Tonight* only appears after 4 PM; before that, the parallel section is *Today*.
2. **Place is the wallpaper.** A real Lake Havasu image (Bridge / channel / sunset) anchors the hero. Each section gets a place-cue (a small line drawing of the bridge, a wave glyph for *On the water*, etc.).
3. **Browse and chat are siblings.** Category tiles and "See all" routes go to filterable list pages, *not* into chat. Chat remains the primary entry from the hero composer.

### B2. Tokens — Ocean tide (drop-in replacement for `:root` in `home.css`)

Palette decision: **Ocean tide**, sourced from codeska's 2026 list and adapted for Hava. Lake-first — the page wallpaper is cool mist (the channel at first light) rather than warm paper. Teal stays primary at depth (the brand water color); clay stays as the editorial secondary accent; sun-coral is reserved for live/urgent. The dark "On the water" inverted block uses its own `--bg-3` token at a deeper night-ink value to match the cooler base. Comparison page: `palette-options.html`.

```css
:root {
  /* surface — Ocean tide */
  --bg:        #eaf4f4;   /* mist — channel at first light */
  --bg-2:      #c4dde4;   /* tide wash, used on feature blocks */
  --bg-3:      #0a2228;   /* night ink, used in inverted sections */
  --paper:     #ffffff;

  /* ink scale — verified AA against --bg #eaf4f4 */
  --ink:       #0a2228;   /* primary text */
  --ink-2:     #33545b;   /* body copy */
  --ink-3:     #4d6c74;   /* meta / labels (≥4.5:1 on --bg) */
  --ink-4:     #8aa5ad;   /* meta only — never body copy */

  /* primary — Lake Havasu water at depth (unchanged: brand water color) */
  --water-50:  #d8eaeb;
  --water-100: #a3d4d4;
  --water-300: #5fa6b3;
  --water:     #0e6e7c;
  --water-700: #064551;

  /* secondary — desert clay (terracotta) — editorial accent */
  --clay-50:   #fae3d6;
  --clay:      #b8623d;
  --clay-700:  #7a3a1f;

  /* accent — sunset coral (live/urgent only — earns the user's eye) */
  --sun:       #e8654a;
  --sun-soft:  rgba(232, 101, 74, 0.12);

  /* status */
  --ok:        #4a7d44;   /* "open" */
  --ok-soft:   rgba(74, 125, 68, 0.10);
  --warn:      #c87a18;   /* "closing soon" */

  /* rules — tinted to the night-ink base, not warm-ink */
  --rule:      rgba(10, 34, 40, 0.10);
  --rule-soft: rgba(10, 34, 40, 0.05);

  /* shadows — water-realistic, slightly cooler than paper-realistic */
  --shadow-1:  0 1px 2px rgba(10, 34, 40, 0.05);
  --shadow-2:  0 8px 24px -12px rgba(10, 34, 40, 0.18), 0 1px 2px rgba(10, 34, 40, 0.06);
  --shadow-3:  0 24px 48px -20px rgba(10, 34, 40, 0.25), 0 2px 6px rgba(10, 34, 40, 0.07);

  /* radii */
  --radius-sm: 10px;
  --radius:    16px;
  --radius-lg: 28px;

  /* type */
  --sans:  "Inter", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  --serif: "Fraunces", "Source Serif 4", Georgia, serif;
  --mono:  ui-monospace, "SF Mono", Menlo, monospace;

  /* type scale */
  --t-eyebrow: 11px;
  --t-meta:    13px;
  --t-body:    16px;
  --t-lede:    18px;
  --t-h3:      22px;
  --t-h2:      32px;
  --t-h1:      clamp(48px, 9vw, 112px);
}
```

What this changes vs. the current live site:

- **Background flips from warm paper (`#f7f5ef`) to cool mist (`#eaf4f4`).** The page now feels like the channel at first light rather than a Sunday paper. This is the headline change of the palette.
- **Ink scale shifts to a cool-blue base** (`#0a2228` instead of `#14140f`) so type doesn't fight the cool background. `--ink-3` darkened from the live `#6e6e67` to `#4d6c74` to maintain ≥4.5:1 contrast on the new `--bg`.
- **`--bg-2` is a tide wash** (`#c4dde4`) instead of a sunset wash. Used on the lighter half of feature card image fallbacks and the hero glow.
- **`--bg-3` is a deeper night-ink** (`#0a2228`) than the previous `#1a2a33`. The "On the water" inverted block still works but reads as truer-night/water-deep rather than slate.
- **Teal primary unchanged** (`#0e6e7c`). Brand-critical token; the lake's color is fixed.
- **Clay accent unchanged** (`#b8623d`). The editorial warm note survives intact and is the only saturated warm color on the page now — which is the entire reason to keep it.
- **Sun-coral and ok/warn unchanged**. Status semantics don't depend on the palette shift.
- **Rules and shadows tint to the night-ink base** instead of a warm-ink base, so the "feel" of the chrome aligns with the new background even at low intensities.

WCAG note: every ink/bg pair in this token set has been spot-checked at 4.5:1 minimum for body and 3:1 for large text. The ink-3 darkening (`#5d5d56` → `#4d6c74`) is non-cosmetic; on the cooler bg it's necessary to hold AA at 14px.

### B3. Type system

Keep Inter + Fraunces — they're a strong pairing. Use them more deliberately:

| Use | Family | Size | Weight | Optical size | Notes |
|---|---|---|---|---|---|
| Display H1 (hero) | Fraunces | `--t-h1` | 300 | 144 | italic accent allowed; the `*Havasu*` move repeats once per page max |
| Section H2 | Fraunces | `--t-h2` | 400 | 100 | always sets a section, always paired with a left rule + sub-line |
| Card title H3 | Fraunces | `--t-h3` | 400 | 60 | consistent across all card variants |
| Lede / pull quote | Fraunces italic | `--t-lede` | 300 | 60 | Hava's voice |
| Body | Inter | `--t-body` | 400 | — | line-height 1.55 |
| Meta / eyebrow | Inter | `--t-meta` / `--t-eyebrow` | 500 | — | tracking +0.18em on eyebrows only, never on meta |
| Code/data (rare) | mono | `--t-meta` | 400 | — | for `/events/UUID`-style strings if they ever surface |

**Rule:** never set tracking on running prose (the current footer meta is `letter-spacing: 0.16em` on real city names — kills readability). Tracking is for eyebrows and small-caps section labels only.

### B4. Layout — a 12-column, magazine-paced grid

Current page is "stacked rows of 3-up cards." Instead, alternate scale and texture:

```
┌──────────────────────────────────────────────────────────┐
│  Topbar — wordmark · place + date · search shortcut · login │
├──────────────────────────────────────────────────────────┤
│                                                          │
│       HERO  (real photo, full-bleed gradient overlay)    │
│       Greeting that reads the time of day                │
│       Composer + 4 chips (not 7)                         │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  HAVA'S READ  ──────  pull quote, italic, signed, dated  │
├──────────────────────────────────────────────────────────┤
│  TONIGHT  (or TODAY before 4pm)                          │
│  ┌──────────────┬──────────────┬──────────────┐          │
│  │  Big card    │  Small card  │  Small card  │          │
│  │  (image, blurb│  (compact)   │  (compact)   │          │
│  │   in Hava's   │              │              │          │
│  │   voice)      │              │              │          │
│  └──────────────┴──────────────┴──────────────┘          │
├──────────────────────────────────────────────────────────┤
│  CATEGORIES — pill grid w/ glyphs (not bullet circles)   │
├──────────────────────────────────────────────────────────┤
│  LOCAL PROS · SPOTLIGHT (clearly marked, smaller scale)  │
│  3-up but visually quieter than editorial sections       │
├──────────────────────────────────────────────────────────┤
│  THIS WEEK — 7-day strip (one row per day, mini cards)   │
├──────────────────────────────────────────────────────────┤
│  ON THE WATER — inverted dark section with sunset photo  │
│  (variety: breaks vertical monotony)                     │
├──────────────────────────────────────────────────────────┤
│  NEW ON HAVA — small list, not card grid                 │
├──────────────────────────────────────────────────────────┤
│  CONTRIBUTE — minimal, two buttons: Add a place / Pitch  │
├──────────────────────────────────────────────────────────┤
│  FOOTER                                                  │
└──────────────────────────────────────────────────────────┘
```

Reasoning:

- **Two reading rhythms.** Sections alternate between *dense card grid* and *editorial single-column blocks*. Today, every section is a 3-up grid — no rest.
- **A dark inverted block.** *On the water* in `--bg-3` ink with a Pittsburg Point sunset photo gives the page a second register and breaks the tan paper monotony. It's a place-cue, not a row of records.
- **Week strip ≠ 3-up grid.** "This week" is naturally 7 days of horizontal pacing. Render it as a 7-row mini-list (Mon / Tue / Wed…) with one or two events per day, not three giant cards repeating the same Aquatic Center.
- **Categories as pills with glyphs.** Replace identical bullet circles with simple line icons (drop, fork, wrench, sun, paw, scissors, etc.) and use sentence-case human labels.

### B5. Components

#### B5.1 Card variants

Three card families, not four:

- **Editorial card** — used by *Tonight* big card and *On the water* feature. Image is hero, title is Fraunces 28–36, blurb is up to 220 chars *of Hava's voice*, footer is venue + time, badge = "Hava's pick" only when editorially curated.
- **Listing card** — used by *Local pros* and event side cards. Image is square or 4:3, title is Fraunces 22, status pill (`--ok`/`--warn`/`--sun`) replaces the generic meta line, footer is single tap target (call / map / save).
- **Row item** — used by *This week* and *New on Hava*. No image. Compact: time + title + 1-line blurb + arrow. Designed to scan 12+ in a column.

Every card gets:
- `:focus-visible` outline `2px solid var(--water)` with `4px` offset.
- `prefers-reduced-motion: reduce` removes hover translation.
- Real `width`/`height` on images, plus `loading="lazy"` and a `srcset`.

#### B5.2 Status pill (rebuilt with semantics)

| State | Background | Text | Dot | When |
|---|---|---|---|---|
| `open` | `--ok-soft` | `--ok` | `--ok` | within hours, ≥30 min until close |
| `closing-soon` | `rgba(200, 122, 24, 0.12)` | `--warn` | `--warn` | within 30 min of close |
| `live` | `--sun-soft` | `--sun` | `--sun` | event currently happening |
| `closed` | `--rule-soft` | `--ink-3` | `--ink-4` | outside hours |
| `unknown` | none | `--ink-3` | none (no dot) | hours not on file — render as plain text "Hours on profile", no pill |

Rule: never show a pill we can't justify with data. The current "Open · Hours on profile" should become plain meta text without a pill.

#### B5.3 Composer

- Stays the centerpiece of the hero.
- Becomes a controlled component: when focused, expands to show a *recent searches* drawer + 3 *Hava suggests* prompts driven by the hour of day.
- Submits with `fetch` to `/api/chat` and routes to `/chat` only on success — no full-page nav on Enter.
- Loading state shows a Hava-voiced "Hava's pulling that up…" with a 3-dot animation in the composer right side.
- **Placeholder cycles through example queries on idle.** See §B5.3.1 below.

#### B5.3.1 Placeholder cycling

The composer placeholder demonstrates breadth without taking screen real estate. On page load it shows the framing line (*Ask Hava — what's open, what's on, who to call…*); after a 3-second dwell it begins cycling through specific example queries every 4 seconds with a 280 ms crossfade.

**Lifecycle:**

```
page load
  → show initial framing line
  → wait 3000ms (HOLD_INITIAL_MS)
  → fade to first example (280ms)
  → hold 4000ms (HOLD_PER_MS)
  → fade to next example
  → loop indefinitely

input focused
  → stop cycling
  → restore initial framing line if input is empty

input blurred
  → if input is empty, restart cycling

prefers-reduced-motion: reduce
  → never cycle, hold initial framing line forever
```

**Implementation:** `app/static/js/home-composer.js` swaps `input.placeholder` and animates `input.style.opacity` (the input is empty during cycling, so opacity transitions safely affect only the placeholder text). The example list is randomised on each page load so users don't see the same first example.

**Locked example list (10 queries — audit-verified).** Order is randomised at runtime, but the set is fixed. Every example below maps to a documented intent in `app/chat/intent_classifier.py` or a structured filter in `app/chat/tier2_db_query.py` (Tier2Filters schema), so tapping any one returns a satisfying answer with the data and intent surface that exists today. **Updating the set requires running the same audit** — adding a query the backend can't answer is a trust regression, not a feature.

| # | Example | Intent / filter that handles it |
|---|---------|---------------------------------|
| 1 | `Ask Hava — What's going on tonight?` | `time_window=today` (events) |
| 2 | `Ask Hava — Find me a plumber` | `LIST_BY_CATEGORY` (plumber is a clean Google Places primary category) |
| 3 | `Ask Hava — When does the Aquatic Center open?` | `HOURS_LOOKUP` for specific entity (Tier 1) |
| 4 | `Ask Hava — What's open right now?` | `OPEN_NOW` intent (filters on `hours_structured`) |
| 5 | `Ask Hava — Kids yoga in town` | Programs filter on `age_min`/`age_max` + `activity_category=yoga` |
| 6 | `Ask Hava — Coffee shops on McCulloch` | `LIST_BY_CATEGORY` + `location` substring filter |
| 7 | `Ask Hava — What's on this weekend?` | `time_window=this_weekend` (events) |
| 8 | `Ask Hava — What time does Mudshark close?` | `HOURS_LOOKUP` for specific entity (Tier 1) |
| 9 | `Ask Hava — Library hours for Saturday` | `HOURS_LOOKUP` + `day_of_week=saturday` |
| 10 | `Ask Hava — Programs for 8-year-olds` | `AGE_LOOKUP` on Programs (overlap detection on `age_min`/`age_max`) |

**Why these ten:**

- *Demonstrates breadth* — the verticals span events (tonight, weekend), services (plumber, coffee shops), info lookups (hours, day-specific hours), and audience filters (kids yoga, programs by age). A user reading any three consecutive cycles understands Hava is not a single-purpose tool.
- *Voice-aligned* — each query reads like a real person typing what they want, not a search-keyword string. *"What's open right now?"* and *"Find me a plumber"* both demonstrate that Hava handles conversational shapes — first-person needs, casual phrasing, time-of-day cues — rather than requiring structured queries.
- *Locality-aware* — *"Mudshark"*, *"Aquatic Center"*, and *"on McCulloch"* anchor specific Lake Havasu context that a generic search bar wouldn't surface, reinforcing the *Lake Havasu's local* positioning.
- *Backend-honest* — every query has been verified against the data model. No placeholder lies. If the example list and the chat capability ever drift apart, the rotation becomes worse-than-useless because each tap that fails to deliver is a trust regression specifically caused by the placeholder promise.

**Capitalization** is sentence-case for each example (matching how users actually type), with proper-noun capitalisation preserved (*Mudshark*, *Aquatic Center*, *McCulloch*). The "Ask Hava — " prefix is persistent across all examples so the brand call-to-action reinforces every cycle.

**Accessibility:** the cycling halts on focus and respects `prefers-reduced-motion`. Screen readers don't read placeholder changes mid-cycle (the input still has `aria-label="Ask Hava"`), so SR users get the static framing line and aren't interrupted by the rotation.

#### B5.3.2 Future placeholder candidates (require capability work)

The following queries are *the high-value Lake Havasu local-guide questions* a knowledgeable local would obviously answer — but they cannot ship in the placeholder rotation today because the schema and intent layer don't yet support them. They are the goalposts, not pretend-features. Each is held out of the rotation until the corresponding capability exists.

| Future query | Capability needed |
|--------------|-------------------|
| `Date night under $50` | (a) `price_level` field on Provider — single Places API field-mask change in `app/contrib/places_client.py` (currently omitted for cost control); (b) editorial atmosphere tags (`romantic`, `intimate`); (c) `DATE_NIGHT` intent in `intent_classifier.py` combining food_drink + atmosphere + price ceiling |
| `Sunday brunch with a view` | Editorial atmosphere tags (`view`, `patio`, `waterfront`) on Provider, populated by the contribution moderation flow |
| `Find me a plumber that picks up` | Response-time / SLA field on Provider, ideally derived from review-text sentiment ("they answered fast") since direct measurement is hard |
| `I want tacos` | Cuisine sub-category on Provider beyond the `food_drink` parent — either (a) parse Places `types[]` array more aggressively (currently dropped to reduce false positives in 2026-05-08 voice battery fix), or (b) add an editorial `cuisine` tag set |
| `I need an HVAC tech` / `pool builder` | Better category disambiguation — many specialty trades are tagged `general_contractor` in Google Places. Either (a) editorial sub-category tagging at contribution time, or (b) NLP over `Provider.description` to extract specialty hints |
| `Activity for my kids after school` | This one is *partially* answered today via Programs age filtering, but the "after school" temporal hint requires a `school_dismissal_window` time computation that doesn't exist. Could ship by treating "after school" → `time_window=after_3pm` when paired with an age filter ≤14 |

These are tracked in `docs/BACKLOG.md` under a new "Placeholder rotation aspirations" heading. Each entry has a concrete schema/intent change attached so when prioritisation comes around, the work is decomposed and ready to estimate.

#### B5.4 Category tile

- Uses a 24×24 line glyph (Lucide-style) sized to optical centre with the label.
- Label is **sentence case from a copy table**, never the DB slug. Add a `CATEGORY_LABELS: dict[str, str]` map in `app/home/queries.py`.
- Hover/active uses `--water-50` background instead of border-only treatment.

#### B5.5 Place-cue divider

A small SVG glyph (the London Bridge silhouette, a wave, a compass rose) renders between major sections instead of a flat 1px rule. Adds atmosphere; cheap to implement; doesn't compete with content.

### B5.6 Ad inventory (replaces "Hava's Read" slot with monetisation)

The AI-generated *Hava's read on tonight* is removed entirely (editorial liability, canned text on every refresh, no information value). The page contracts in that location — no editorial tagline replacement; brand voice lives in chat, in card blurbs, and in section copy. Hava on /home is structural, not vocal.

The four-tier inventory below replaces it (revised down from an earlier five-tier proposal that was oversold for the page's scale):

| Tier | Surface | Where | Cards / slot | Disclosure | Price tier |
|---|---|---|---|---|---|
| 1 | **Marquee sponsor** | Below *Today* | 1 / day | `Ad` eyebrow + "Sponsored by …" attribution | premium |
| 2 | **Spotlight grid** | *Local pros · Spotlight* | 2 / week (was 3) | `Spotlight` badge on card | mid |
| 3 | **In-feed Promoted card** | *Today* OR *This week* | max 1 per page (was 1 per row) | `Ad` chip in eyebrow + clay left-edge bar on card | mid |
| 4 | **Supporters wall** | Footer | up to 4 logos (was 6) | "Hava is supported by …" | volume |

**Marquee position:** below *Today*, not below the hero. The user reads at least one editorial row before encountering paid content. Trust premise > impression count. (Section underwriter — formerly Tier 4 — is dropped: it doubled with Marquee and Supporters and earned no real differentiation at this scale.)

**Disclosure copy is consolidated to two words.** *Ad* for in-feed surfaces (Marquee, Promoted). *Supporter* for off-feed (Supporters wall). The price tier lives in the visual treatment, not the disclosure word. FTC native-ad guidance prefers consistent plain-language disclosure; varying the word across tiers is design variety masquerading as clarity.

Hard rules across every tier:

- **Disclosure is always visible**, never on hover, never abbreviated, never euphemised. No "Featured," no "Recommended," no "Editor's pick" on paid surfaces.
- **Editorial outranks sponsor visually.** Editorial cards get a `1px` left edge in `--water` and a `--shadow-2` lift; same-row Promoted cards get a `1px` left edge in `--clay` and a flat `--shadow-1`. Two cards side by side, the editorial one wins your eye. This is a real differentiator — same shape, different weight — not just a badge swap.
- **One Promoted card max per page.** Not per row — per *page*. If we sell two for the same week, they alternate days. Saturating the editorial sections breaks trust faster than missing a slot breaks revenue.
- **Local-only until $2k MRR or 90% sold local inventory, whichever comes first.** Sponsors must be Lake Havasu City businesses through that threshold. No display network, no programmatic, no remarketing pixels. Stated trigger so the rule doesn't erode under revenue pressure without explicit decision.
- **No third-party trackers in served HTML.** Our own click endpoint (`/sponsor/click?slot=…&id=…`) is fine; ad-tech beacons are not. Note: Google Fonts is loaded by the page already and is itself a Google tracking surface — call out for follow-up (self-host Inter and Fraunces from `/static/fonts/` to remove this dependency).
- **A single advertiser can hold at most 2 tiers concurrently** — enforced as a unique constraint in `Sponsor` model, not just a written rule.

**AI content policy.** AI summarisation of factual content (event titles, hours, locations, schedules) is acceptable. AI editorialising (opinions, picks, mood pieces, taglines) is not. Anywhere "Hava's pick," "editor's choice," or similar curatorial language appears, the underlying call must be a human, not an LLM. Card-blurb cleanup via `tier3_postprocess` is permitted because it summarises factual descriptions; it must not be repurposed to generate opinions or curatorial copy.

#### Tier 1 — Marquee sponsor (sits below *Today*)

Daily inventory, one advertiser per day. Renders as an editorial-shaped card on warm paper with:

- A 4:3 photo (advertiser supplies, we crop), `--clay-50` background tint when no photo provided.
- Eyebrow row: `SPONSOR · Lake Havasu City` in `--ink-3` +0.22em tracking, with a plain-language `Ad` chip on the right edge of the eyebrow row.
- Headline (Fraunces 22, advertiser-written, 60-char limit) — never AI-rewritten. Hava does not put words in a sponsor's mouth.
- 1-line pitch (Inter 14, 120-char limit).
- CTA button (Visit · Call · Map · Menu — advertiser picks one), `--ink` background, hovers to `--clay`.
- Right-edge attribution: "Sponsored by [Business name]" — reinforces disclosure for screen readers if the eyebrow is skipped.

**Sold-state vs unsold-state size.** When sold, the Marquee is the photo + body + CTA card described above. When unsold, the slot **shrinks** to a single line — same eyebrow ("SPONSOR · LAKE HAVASU CITY · Ad"), no photo, no card, just a thin "Become the marquee sponsor →" link in `--ink-3`. The page contracts when inventory's empty rather than displaying a guilty band of unsold capacity. This is the inverse of the previous proposal (which expanded the empty slot into a CTA card) and protects the brand from advertising its own sales failures.

#### Tier 2 — Spotlight grid

**Two cards** in *Local pros · Spotlight* (down from three; the row was visually outranking editorial). Card height uses `--radius` (not `--radius-lg`); section heading uses Inter 600 13px (not Fraunces 22) so the row reads as a commercial sub-block rather than a hero row. Sell weekly.

#### Tier 3 — In-feed Promoted card

Up to **one Promoted card per page** (not per row). Lives in either *Today* or *This week*, never both. Visual treatment:

- **Left-edge bar in `--clay`**, 3px wide, full card height. This is the primary visual disclosure — visible from across the page, not just at meta-line scanning distance.
- Eyebrow takes the form `Ad · 5pm · Java on Main` — `Ad` first, in clay text, comma-separated. Not a pill in the middle of the meta line where it can slide past.
- Card otherwise organic in shape and shadow, but uses `--shadow-1` (flat) where editorial cards in the same row get `--shadow-2` (lifted). Side-by-side, the editorial card wins the eye.
- Optional `attribution` line in the card footer: "Sponsored by [Business name]" — small, `--ink-3`, present every time.

Skip the slot entirely if no advertiser. An empty in-feed slot is invisible to users; an empty marquee is not.

#### Tier 4 — Supporters wall

Page footer. `Hava is supported by` followed by **up to 4 logos** in a single row (down from 6 — the wall broke on 380px viewports with more logos). Logo style is constrained at write-time: monochrome SVG only, max width 80px, max height 28px, single ink color. Production won't be coherent without these constraints.

Sell monthly. Each logo links to the business's profile or external URL.

#### Moderation workflow (required, not optional)

Every paid surface goes through admin review before publishing. Pipeline:

```
draft (advertiser submits)
  → review (admin sees in /admin/sponsor)
    → approved + scheduled (assigned to a date range, not yet live)
      → live (within scheduled range, served to users)
        → archived (after end_date)
```

Any advertiser-submitted field (headline, pitch, photo, CTA URL) is mutable in `draft` only. Once `approved`, fields lock. An admin can pause a live sponsor with a single toggle (e.g., emergency takedown) — pausing returns the slot to its unsold-state rendering immediately.

#### Performance budget for ad-decorated home page

- **LCP target: 2.5s** on 4G mobile.
- Marquee photo: max 80kb, served as `srcset` 600/1200, preloaded via `<link rel="preload">` when above the fold.
- Ad-related DB queries (Marquee, Spotlight, Promoted, Supporters) cached at 5-minute granularity; cache key includes `now_lake_havasu().replace(minute=now.minute//5*5)`.
- Self-host Inter and Fraunces from `/static/fonts/` (eliminates the Google Fonts third-party dependency *and* lets the fonts cache forever).

#### Self-serve flow (what to build behind the inventory)

The current code has `app/home/sponsor_store.py` and a `/sponsor` route. Extend that, don't replace it. Plan:

```
app/home/sponsor_store.py
  + class AdSlot(Enum): MARQUEE, SPOTLIGHT, PROMOTED, SUPPORTER
  + def active_marquee(now) -> Sponsor | None
  + def active_spotlights(now, limit=2) -> list[Sponsor]      # 2, was 3
  + def active_promoted(now) -> Sponsor | None                # one per page, not per row
  + def supporters(now, limit=4) -> list[Sponsor]             # 4, was 6
  + (note: underwriter helper removed — tier dropped)

app/db/models.py
  Sponsor:
    id, business_id, slot: AdSlot,
    start_date, end_date,
    headline, pitch, photo_url, cta_label, cta_url,
    attribution_text,                # "Sponsored by …" line
    status: Enum(draft, review, approved, live, paused, archived),
    paused_at, paused_reason,
    impressions, clicks,
    created_at, approved_at, approved_by
  UniqueConstraint(business_id, slot, daterange)  # block double-booking
  CheckConstraint(advertiser holds ≤ 2 concurrent slots)

app/sponsor/router.py
  GET  /sponsor                    # public sales page (rate card)
  GET  /sponsor/manage             # advertiser self-serve dashboard (auth)
  POST /sponsor/submit             # creates Sponsor in draft state
  POST /sponsor/buy                # checkout → Stripe (later)
  GET  /sponsor/click?slot=&id=    # 302 to advertiser URL with attribution

app/admin/sponsor_html.py
  - inventory calendar with double-booking detection
  - draft → review → approved pipeline UI
  - one-click pause / resume
  - fill-rate metrics, click/impression CSV export
```

The Marquee CTA *"This slot is open · Reach locals at the moment they're planning their day"* stays in place as the empty-state fallback for the Marquee slot, but the call-to-action goes to a real `/sponsor` rate-card page (today it's a placeholder route).

Pricing direction (to decide separately, not part of this UI spec): marquee weekly > spotlight weekly > promoted-card weekly > underwriter weekly > supporter monthly. Local rates likely $50-$300/week range based on comparable small-town newsletter ad markets; the pricing page should be A/B-testable.

#### Replacing Hava's Read

The blockquote section (`<section class="read">` in `home.html`, the `read` block in `home.css`, and the `hava_read` data assembly) gets removed entirely. Specifically:

- Delete the `read` section from `app/templates/home.html`.
- Delete the `.read` CSS block (~30 lines) from `app/static/styles/home.css`.
- Delete `hava_read` from the home router context dict in `app/home/router.py`.
- Delete or repurpose any `_hava_read` builder in `app/home/queries.py`.
- Replace with a `<section class="marquee">` block driven by `active_marquee(now)`.

If `active_marquee(now)` returns `None` (no sold inventory), render the *Become the marquee sponsor* fallback card rather than nothing. The page should never have an empty band where the marquee would be — the eye expects a reading rest after the hero.

### B5.7 Locked copy

These exact strings ship as written. Do not paraphrase, A/B-test, or hand to an LLM for "polish" without a written decision to revisit them.

| Slot | Copy |
|---|---|
| Topbar wordmark | `Hava` |
| Topbar dateline | `Lake Havasu City · [date]` (computed) |
| Hero eyebrow | (none — dropped; the topbar dateline already orients the user, and the mission line below the H1 is the page's strongest secondary statement) |
| Hero H1 | `Ask *Hava*.` (italic on *Hava* in `--water-700`; period included) |
| Hero mission | `Search Local. Support Local. Lake *Havasu*.` (Fraunces 24, regular weight, italic + `--water-700` on *Havasu* — visual rhyme with H1) |
| Hero utility (was lede) | (moved to chips — see below) |
| Hero chips (3 fixed) | `Today` · `This Weekend` · `With the Family` (Title Case — chips function as button labels, not prose) |
| Chip → query map | `Today` → `what's on today` · `This Weekend` → `what's on this weekend` · `With the Family` → `what to do with the family` |
| Composer placeholder | `Ask Hava — what's open, what's on, who to call…` |
| Marquee eyebrow (sold) | `SPONSOR · LAKE HAVASU CITY` + `Ad` chip |
| Marquee fallback line | `SPONSOR · LAKE HAVASU CITY · Ad` + `Become the marquee sponsor →` |
| Promoted eyebrow | `Ad · [time] · [business name]` |
| Spotlight section head | `Local pros · Spotlight` (Inter 600 13px, not Fraunces) |
| Supporters wall label | `Hava is supported by` |
| Page footer mission | `Hava is your local. Better than search, kinder than scrolling Facebook, always answering in 1–3 sentences.` |

The hero is structured in three layers, each with a single job. The H1 (*Ask Hava.*) is the brand call-to-action — short, italic on *Hava*, the page's strongest typographic moment at Fraunces 60px / 300 weight / opsz 144. The mission line directly below (*Search Local. Support Local. Lake Havasu.*) is the values statement — Fraunces 24px / 400 weight / opsz 72, with the same italic + `--water-700` color treatment on *Havasu* that the H1 uses on *Hava*, creating a deliberate typographic rhyme. The mission stands as three short declarative sentences — no leading em-dash, no continuation cue — because each beat earns its own period and the cadence (3 syllables · 4 syllables · 3 syllables) reads naturally aloud. The utility entry (what users can ask about) is delegated to the chip row and the composer placeholder; the hero copy itself never repeats the chat-vs-scroll relationship.

The chip row carries three entries, all fixed and Title-cased. Each chip opens a meaningfully different dimension of the product. *Today* and *This Weekend* form a time-gradient (now → near future) that captures both impulse intent and planning intent; users plan ahead more than they impulse-tap, so weekend pulls real value into the hero. *Today* is deliberately broader than *Tonight* would be — it surfaces morning, midday, and evening events alike, so the chip works at any hour rather than ringing hollow before 4 pm. *With the Family* is an audience filter that no vertical chip can capture and that surfaces Hava's contextual judgment (kid-friendly + multi-generational is a cross-vertical answer, not a category). The phrasing is companion-context rather than product-target — locals plan things "to do *with* the family," not "for the family" — so the chip reads as voice-aligned rather than marketing-y. Each chip submits a Hava-voiced query string to `/chat`, not a category slug; the chip → query map is locked in §B5.7.

Title Case rather than lowercase: chips function as button labels, not prose. Lowercase chips read as tags or hashtags rather than tappable calls-to-action and visually fight the sentence-case section heads (*Today*, *This week*) deeper in the scroll. The placeholder text inside the composer (*Ask Hava — what's open, what's on, who to call…*) keeps lowercase clauses because that string *is* prose — flowing inline hint text, a different register from button labels.

The chip row deliberately drops several candidates that earlier proposals included. *on the water* (place identity) — the lake identity is already carried by the wordmark glyph, topbar dateline, italic *Hava* + *Havasu* in the H1 and mission line, and the dark *On the water* feature block deeper in the scroll. *where to eat* — food surfaces naturally inside *Tonight* and *This Weekend* answers; a dedicated food chip would crowd the row at the expense of broader dimensions. *find a pro* (services) — services live in the *Pros & services* section deeper down with proper category browsing, and pushing services into the hero positioned Hava as a directory rather than a discovery product. A contextual time-of-day chip (coffee / open now / happy hour / still open by hour) — the topbar pill and the *Today*/*Tonight* section labels already make the page hour-aware. The proposal also rejects *local businesses* — the entire product is local businesses, so a chip pointing at "local businesses" would be tautological with the *Search Local. Support Local.* mission.

The mission line is also the strategic linchpin between the editorial register and the monetisation surfaces. *Search Local. Support Local.* names the product's purpose; the Marquee, Spotlight, and Promoted tiers in §B5.6 are then visibly part of *supporting local*, not just revenue. The line should be treated as locked copy and not adjusted without revisiting the sponsor program positioning.

### B5.8 Brand expression — Hava without a mascot

**The persona is faceless.** Hava is a name, a voice, and a perspective — not a character with a visual avatar. There is no cartoon, no illustrated character, no photo of a "Hava" person, no animated figure, no chat-bubble face, no stylised initial-letter portrait. Anywhere a competing product would normally insert a mascot, this design holds the line and renders abstract chrome instead.

**The reference is "Ask Jeeves, modernised."** Original Ask Jeeves had a *named* assistant *and* a butler character. The Hava direction keeps the named-assistant convention — the product name and the assistant name are the same; users "ask Hava" — but drops the mascot entirely. Closer contemporary references are how Perplexity, Pi, and Claude.ai surface their assistants: branded by name, voiced by tone, faceless by design.

**Voice register.** Hava is informally modelled on a millennial woman from southern California who has been in Havasu long enough to know which rentals upcharge, which patios catch shade by 4 pm, and which Saturday traffic patterns to avoid. The voice is documented in `docs/persona-brief.md`; the home page surfaces it sparingly. Working notes:

- Contemporary and casual, never formal. Says "the move" before "the recommended option."
- Confident without condescension. Knows the town; doesn't preen about knowing it.
- Contrast beats are the signature: *"The queso's worth it. The parking's not."* / *"Channel'll be glass-still by sunset. Wind kicks up by 1 — go now or go after."*
- Place-name fluency: *McCulloch, the channel, the bridge, Sara Park, Windsor Beach, Body Beach, Pittsburg Point* — these names appear in copy without explanation. Visitors pick them up by context; locals feel seen.
- **Hard "do not" list:** no Southwest climate language. *"Dry heat's no joke," "before the monsoon hits," "the summer sun will cook you," "once the heat kicks in"* — all banned. Temperature references are fine when factually necessary ("it's 110 today, most hikes aren't going to be fun"); climate-as-texture is off.
- No setup-punchline jokes; no performative humour; no exclamation marks in any default copy.

**The five brand touchpoints on /home.** Hava as a brand element appears in exactly five places, and nowhere else:

1. **Wordmark.** Top-left of every page. Abstract teal water glyph (sphere, droplet, or wave — pick one and use it everywhere) plus the name *Hava*. The glyph is the only Hava-specific *visual*; no other graphic identifies her. Sphere is the existing asset; the wave variant in the v2 mockup is acceptable but the choice is one-and-done — pick the glyph in `app/static/img/wordmark.svg` and don't mix.
2. **Hero H1 + mission line.** *Ask **Hava**.* in Fraunces 60px / 300 / opsz 144 with italic on *Hava* in `--water-700`. Directly below, the mission line *Search Local. Support Local. Lake **Havasu**.* in Fraunces 24px / 400 / opsz 72, with the same italic + `--water-700` color on *Havasu* (visual rhyme with H1). Together these are the page's strongest typographic moment and carry both the brand call-to-action and the product's purpose statement. *Search Local. Support Local.* also positions the sponsor program as a values-aligned act, not just monetisation — see §B5.6.
3. **First-person voice in selected copy.** Used sparingly: a few editorial card blurbs in Hava's voice, and the chat empty-state. Most card blurbs do not — first-person is a sparing tool, not a default register. With the H1 now naming the brand, the voice no longer needs to repeat itself in the lede.
4. **"Hava's pick" badge.** Editorial endorsement, used sparingly. Maximum one per row, maximum two on the entire home page. Renders as a small badge with a star glyph + the words *Hava's pick* — never a face, never a portrait, never an avatar. The badge requires human curation per §B5.6 (no AI-generated picks).
5. **Chat name.** Within `/chat`, the assistant identifies as Hava in turn labels and the empty state. The chat surface is where the voice lives most fully; /home leans on the H1 + eyebrow + sparing voice + badge to carry the brand without becoming a character study.

That's the complete list. Anywhere a designer, PM, or future Cursor pass is tempted to add "a Hava avatar," "a Hava character," "a Hava illustration," or "a Hava welcome graphic" — the answer is no. Faceless is a deliberate design constraint with brand-equity reasons (genderless, ageless, raceless, ageless-as-the-product-grows), not an oversight to fill in later.

**Verifying the constraint.** A design pass is correctly faceless if every Hava brand reference is one of the five above and no element renders a humanoid figure (drawn, photographed, animated, or stylised). Audit on every design review. If a future component proposal includes a face, push back before the conversation goes anywhere else.

**One consequence to call out for /chat:** the existing chat empty-state has the line *"I'm your local."* which is good. It does not need a "Hava is typing…" indicator with a head silhouette, an emoji avatar in the message column, or a "Meet Hava" intro screen. The composer placeholder, the message turn prefix (e.g. a small wordmark glyph at the start of Hava's turns), and the voice itself carry the brand. No more than that.

### B6. Page-by-page direction

**Home (`/home`).** As described above.

**Chat (`/chat`).** The current chat is solid (sticky composer, empty state, chips). Two improvements:
- Anchor Hava's first message in *paper* — render it as a torn-paper card with a hand-signed `— Hava` to extend the editorial brand into the chat.
- Add a persistent *home* breadcrumb: "Lake Havasu City · Friday, May 8 · 7:24 AM" so users feel oriented.
- Render component payloads (`day_agenda`, `week_strip`, `card_row`, etc.) using the same component library as the home page — single source of truth.

**Event detail (`/events/UUID`).** Today's `event_permalink.html` was not audited in depth, but the event blurbs surface raw DB strings on home; the detail page almost certainly needs the same content cleanup.

### B7. Photography & illustration

Three image surfaces:
1. **Hero photo** — one curated Lake Havasu landscape (channel, sunset, bridge). Single asset, optimised, served from `/static/img/hero/`.
2. **Event/venue photos** — pulled from Google Places photo refs (the `_provider_image_url` TODO). Cache at our edge to avoid Places API price drift; serve as `srcset` 600 / 1200 / 2000.
3. **Glyphs** — line icons (Lucide MIT-licensed) for categories and dividers. Inline SVG, no icon font.

Until Places photos are wired, use **3 fallback patterns** instead of one tan gradient:
- Topographic line pattern (one-color SVG on `--bg-2`)
- Wave pattern
- Sunset gradient (warmer than current)

Vary by `card.dot` value (teal / warm / live) so cards are visually distinct even when imageless.

### B8. Motion

Keep current restraint. Add one signature motion only: the hero `*Havasu*` italic does a subtle 200ms ink-bleed on first paint (color animates from `--ink` to `--water-700`). Everything else stays at the existing 150–250ms transitions and respects `prefers-reduced-motion`.

### B9. Accessibility deltas

- Replace category enum slugs with human labels (highest impact for screen readers).
- Add `:focus-visible` styles to every interactive element.
- Replace `role="list"`/`role="listitem"` on `<a>` chips with `<ul><li><a>`.
- Confirm `--ink-3` (`#5d5d56`) hits AA on `--bg` at 14 px (≥4.5:1).
- Status pills get an `aria-label` with the same text + an SR-only state ("currently open until 6 PM").
- Hero composer adds visible label "Ask Hava" above the input, not just `placeholder`.

### B10. What to throw out

- The "Live coral" `--live` token (rename to `--sun`, give it real semantics).
- Identical bullet-circle category icons (replace with line glyphs).
- The 180-char description slice in card blurbs (replace with Hava-voiced rewrite via `tier3_postprocess` or a one-line summary column on `Event`).
- Three-cards-per-row template uniformity (replace with magazine pacing).
- Snake-case category labels at *every* surface.
- The "Tonight" filter that includes 5 AM events (split into "Today" before 4 PM, "Tonight" after 4 PM).

---

## Part C — Cursor build plan

Ordered by impact-to-effort. Each step is small enough to do in a single PR. Steps 1–4 fix the *content correctness* problems; everything else is polish / new surface area.

### C1. Fix category labels (smallest, biggest win)

**Files:** `app/home/queries.py`

Add a label table and use it everywhere a category is shown to a user.

```python
# app/home/queries.py — near the top of the module
CATEGORY_LABELS: dict[str, str] = {
    "health_medical":        "Health & medical",
    "food_drink":            "Food & drink",
    "home_services":         "Home services",
    "retail":                "Shops",
    "lake_recreation":       "On the water",
    "professional_services": "Professional",
    "beauty_personal_care":  "Beauty & care",
    "auto":                  "Auto",
    "religion_community":    "Community",
    "fitness_sports":        "Fitness & sport",
}

CATEGORY_QUERIES: dict[str, str] = {
    # what the chip submits to /chat — Hava-voiced, not slug-shaped
    "health_medical":        "find a doctor or clinic",
    "food_drink":            "where should I eat",
    "home_services":         "find a home pro",
    "retail":                "shops in Havasu",
    "lake_recreation":       "what's on the water today",
    "professional_services": "find a pro",
    "beauty_personal_care":  "salons and barbers",
    "auto":                  "auto repair in Havasu",
    "religion_community":    "community and worship",
    "fitness_sports":        "gyms and classes",
}
```

Then in `top_categories()` (the function that materialises the strip), look the slug up in those tables and fall back to title-casing the slug if a key is missing:

```python
human_name = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
human_query = CATEGORY_QUERIES.get(category, f"find a {human_name.lower()}")
```

**Acceptance:** no underscore appears in any user-visible string on `/home`. Run `curl https://…/home | grep -o '_[a-z]'` after deploy — must return nothing.

### C2. Fix the "Tonight" query — **shipped Phase 2A**

Status: **shipped** as part of Phase 2A. `app/home/queries.py` now has a `_TONIGHT_HOUR_THRESHOLD = 16` constant, a `today_section_label()` helper that returns "Today" before 4 PM Lake Havasu time and "Tonight" after, and `tonight()` filters `Event.start_time >= time(16, 0)` after the threshold so 5 AM lap-swim events stop appearing under the Tonight heading. The router passes `tonight_section_label` to the template; `home.html` renders it as the section H2.



**File:** `app/home/queries.py`, function `tonight()`.

Today's filter: `Event.date == today`. Change to time-of-day aware:

```python
def tonight(db: Session, *, limit: int = 3) -> list[dict[str, Any]]:
    """Events later in the same day. Before 4pm we surface 'Today'; after 4pm
    we narrow to events starting between 4pm and midnight."""
    now = now_lake_havasu()
    today = now.date()
    rows_q = db.query(Event).filter(Event.date == today, Event.status == "live")
    if now.hour >= 16:
        rows_q = rows_q.filter(Event.start_time >= time(16, 0))
    rows = rows_q.order_by(Event.featured.desc(), Event.start_time.asc()).limit(limit).all()
    ...
```

Also surface a `label_override` on the section so the template can render *Today* before 4 PM and *Tonight* after.

**Acceptance:** at 8 AM, `/home` shows "Today" with morning events filtered out and the label = "Today." After 4 PM the label flips to "Tonight" and all returned events start at or after 16:00.

### C3. Replace card blurb text with summaries

**Files:** `app/db/models.py`, `app/home/queries.py`, optionally a small migration.

Two-step plan, do step 1 first since it's reversible:

1. Add a `summary: Mapped[str | None]` column on `Event` (≤140 chars). Backfill with a one-line Hava-voiced summary via a script that runs `tier3_postprocess` on the long description. The home page reads `summary` if set, else falls back to a *truncated, URL-stripped, first-sentence* of `description`.
2. In `_card_blurb(event)` helper (new): strip URLs, strip `\n\n+`, take first sentence, truncate at 140 chars with an ellipsis at a word boundary.

```python
import re
_URL_RE = re.compile(r"https?://\S+")

def _card_blurb(event: Event) -> str:
    if event.summary:
        return event.summary
    raw = (event.description or "").strip()
    raw = _URL_RE.sub("", raw)
    raw = re.sub(r"\s+", " ", raw)
    first = raw.split(". ")[0].strip().rstrip(".")
    if len(first) > 140:
        first = first[:137].rsplit(" ", 1)[0] + "…"
    return first
```

**Acceptance:** no card blurb on `/home` contains `http`, `\n`, or an ISO date.

### C4. Fix the Farmers Market card (and any other CSV-shaped descriptions)

**File:** `app/contrib/*` (whichever ingestion script wrote that record), and `app/home/queries.py` as a defensive read.

Server-side: in the description-cleaner, detect "Date: …\nTime: …\nVenue: …" patterns and discard them — those should populate structured columns, not the description. Read-side: `_card_blurb` should already handle this once URLs and newlines are stripped, so this is mostly a write-time fix.

**Acceptance:** no card blurb shows the substring `Date:` or `Venue:` followed by a colon-prefixed list.

### C5. Drop tokens, swap palette, fix `--ink-3`

**File:** `app/static/styles/home.css` (and `chat.css` for parity).

Replace the `:root` block with the tokens in §B2. The change is mostly additive: existing variable names continue to work where they appear, but new ones (`--bg-3`, `--water-300`, `--clay-50`, `--shadow-2`, `--shadow-3`, `--radius-sm/lg`) become available.

Run a lighthouse-color-contrast pass on the new `--ink-3` value over `--bg`.

**Acceptance:** every existing component still renders; nothing visibly regresses; `--ink-3` over `--bg` at 14 px reports ≥4.5:1.

### C6. Replace bullet-circle category icons with line glyphs

**Files:** `app/templates/home.html`, new `app/static/icons/categories/`, `app/home/queries.py`.

Drop in 10 Lucide-style line SVGs (24×24, `stroke="currentColor"`, no fill) — one per category. Map `Provider.category` slug → glyph filename in the same dict pattern as `CATEGORY_LABELS`. Render as an `<svg>` `<use href="#cat-water"/>` if you want to share the sprite, otherwise inline.

```jinja
<a class="cat-tile{% if cat.warm %} warm{% endif %}" href="/categories/{{ cat.slug }}">
  <span class="ic">{{ cat.glyph_svg|safe }}</span>
  {{ cat.label }}
</a>
```

**Acceptance:** every category has a distinct glyph; categories without a known glyph fall back to a generic compass rose.

### C7. Wire event/provider photography (or use varied fallbacks)

**Files:** `app/home/queries.py` (`_provider_image_url`), new `app/core/places_photos.py`, `app/static/img/fallback/`.

Two modes — pick one:

- **Real photos.** Implement `_provider_image_url` and a parallel `_event_image_url`. Cache Places photo blobs in our own bucket; serve through `/img/cache/...`. Add `srcset` 600/1200/2000.
- **Stylised fallbacks (until photos ship).** Replace the flat tan gradient with one of *three* SVG patterns picked deterministically from event ID hash: topographic lines, waves, sunset. Vary the dominant colour by `card.dot` (`accent`/`warm`/`live`).

Pick fallback mode for the next sprint, real photos for the one after.

**Acceptance:** no two adjacent cards on `/home` show the same image surface.

### C8. Magazine-pace the page (layout swap)

**File:** `app/templates/home.html`.

- *This week* → 7-row day strip (`grid-template-columns: 80px 1fr;` per day, no images).
- Add new *On the water* section: full-bleed dark block (`--bg-3`), one feature card on a sunset photo background.
- *New on Hava* → row-list rather than 3-up grid (5–7 items, 1-line each).
- Insert place-cue dividers (small SVG glyph centred between sections) instead of section-margin gaps.

**Acceptance:** vertically scanning the page, you should encounter at least 4 distinct visual rhythms (hero, pull quote, 3-up grid, day strip, dark block, list).

### C9. Status pill rebuild

**Files:** `app/home/queries.py` (`_hours_status`), `app/static/styles/home.css`.

Implement the four real states from §B5.2. When data is absent, render plain meta text — no pill.

**Acceptance:** removing all `Provider.google_hours` rows from a test DB does not produce any "Open" pills.

### C10. Browse pages (un-bottleneck the chat)

**Files:** new `app/home/category_router.py`, new `app/templates/category.html`.

Each category gets a static-feeling listing page at `/categories/{slug}` (e.g. `/categories/home-services`). Same card library as home; pagination at 24 per page; filters: open-now, distance, price-tier (when known).

**Acceptance:** clicking a category tile no longer requires typing a chat query to see the underlying list.

### C11. Composer polish

**File:** `app/static/js/home-composer.js` (new).

Progressive enhancement: when JS loads, intercept the composer submit, fetch `/api/chat`, route to `/chat` with the response prepopulated. Show a 1-second loading state in Hava's voice ("Hava's pulling that up…"). On focus, expand a recent-searches drawer (last 5 from `localStorage`).

Also implement the placeholder cycling pattern from §B5.3.1: 10 locked examples, randomised order, 3000ms initial dwell, 4000ms per-example dwell, 280ms crossfade, halt on focus, resume on blur with empty input, never run when `prefers-reduced-motion: reduce` matches.

**Acceptance:**
- Enter from the home composer no longer triggers a full page refresh when JS is loaded; it does still work as a plain GET when JS is off.
- Placeholder cycles through the 10 examples in §B5.3.1 with the timing and behavior specified there.
- Cycling stops within one frame of `focus`; restarts within `HOLD_INITIAL_MS` of `blur` when the input is empty.
- `prefers-reduced-motion: reduce` produces no cycling at all (verified in DevTools).

### C11b. Remove Hava's Read; add Marquee slot below *Today*

**Files:** `app/templates/home.html`, `app/static/styles/home.css`, `app/home/router.py`, `app/home/queries.py`, `app/home/sponsor_store.py`, new `app/templates/_partials/marquee.html`.

1. Delete the `read` section block from `home.html` and the `.read` CSS block from `home.css`.
2. Drop `hava_read` from `app/home/router.py`'s context dict and any `_hava_read` builder in `queries.py`.
3. Insert the new Marquee partial **after** the *Today* section (not above it).
4. Add `active_marquee(now)` to `sponsor_store.py` returning a `Sponsor` or `None`.
5. New `marquee.html` partial: sold-state renders the full editorial-shaped card; unsold-state shrinks to a single eyebrow + link line.

**Acceptance:** the `read` class no longer appears in CSS or rendered DOM; the Marquee section sits below *Today* (not below the hero); when no `Sponsor` is active for the marquee slot, the page contracts to a one-line eyebrow rather than expanding to a CTA card.

### C11c. Build remaining inventory tiers (Spotlight, Promoted, Supporters)

**Files:** `app/home/sponsor_store.py`, `app/db/models.py`, `app/templates/home.html`, `app/static/styles/home.css`, `app/sponsor/router.py`, `app/admin/sponsor_html.py`.

Build in order: Spotlight refinement (down to 2 cards) → Promoted in-feed (one per page, max) → Supporters wall (4 logos max). The Underwriter tier is **dropped** from the original proposal — do not implement it.

Wire all paid surfaces through a single `disclosure_label(slot)` helper that returns either `"Ad"` (Marquee, Promoted) or `"Supporter"` (Supporters wall). Spotlight retains its `Spotlight` badge as a card-level treatment, not as the disclosure word.

Editorial-vs-paid visual differentiation rule, applied in CSS:

```css
.card.editorial { border-left: 1px solid var(--water); box-shadow: var(--shadow-2); }
.card.promoted  { border-left: 3px solid var(--clay);  box-shadow: var(--shadow-1); }
```

**Acceptance per tier:**

- *Spotlight*: section header uses Inter 600 13px, not Fraunces; section reads as commercial sub-block. Exactly 2 cards live at once.
- *Promoted*: at most one Promoted card on the entire page (not per row). Card has the 3px clay left edge, the `Ad · …` eyebrow format, and `--shadow-1` (flat). No card has both `Promoted` and `live` states.
- *Supporters wall*: footer shows 1–4 logos when sold; hidden entirely when zero. Each logo is monochrome SVG, max 80×28px.

### C11d. Moderation + admin pipeline

**Files:** `app/admin/sponsor_html.py`, `app/sponsor/router.py`, `app/db/models.py`.

Implement the full draft → review → approved → live → archived state machine. Admin sees pending drafts in `/admin/sponsor`, can approve/reject (rejection requires a comment back to the advertiser), can pause any live sponsor with one click. Approval locks all advertiser-editable fields.

**Acceptance:** no `Sponsor` row with `status != approved` is ever served to /home. Pausing a live sponsor mid-day flips it to unsold-state on the next page render (≤5 min, given the cache budget).

### C11e. Performance budget for ad-decorated home page

**Files:** `app/templates/base.html` (or wherever the `<head>` lives), `app/home/sponsor_store.py`, `app/static/fonts/` (new).

1. Self-host Inter (variable) and Fraunces (variable) under `/static/fonts/`. Replace the Google Fonts `<link>` with `@font-face` declarations using `font-display: swap`. Adds two HTTP requests but eliminates a third-party tracking surface and lets the fonts cache forever.
2. Marquee photo: `<link rel="preload" as="image" href="…" imagesrcset="…">` in `<head>` whenever a sponsor is active. Cap photo at 80kb on upload (validated server-side).
3. All `active_*` helpers wrap their query in `@lru_cache` with a 5-minute key (`now.replace(minute=now.minute//5*5)`).

**Acceptance:** `/home` LCP ≤ 2.5s on simulated 4G mobile (Lighthouse). Network tab shows zero requests to `fonts.googleapis.com` or `fonts.gstatic.com`. Marquee photo file size ≤ 80kb.

### C11f. Sponsor self-serve and admin

**Files:** `app/sponsor/router.py` (new public sales page + draft submit), `app/admin/sponsor_html.py` (inventory calendar).

Build the public `/sponsor` rate-card page (4 tiers, starting prices, "Get in touch" form), the `/sponsor/submit` POST that creates a Sponsor in `draft` state, and the admin inventory calendar. Stripe checkout deferred to a follow-up.

**Acceptance:** a non-admin user can submit a draft from `/sponsor`; an admin can review and approve it from `/admin/sponsor`; once approved and scheduled, the sponsor appears on `/home` within one page render.

### C12. Footer & meta

**File:** `app/templates/home.html`.

- De-duplicate the *List your business* / *Sponsor a slot* links.
- Move *About Hava* and *Privacy* into a "small print" line below the main mission line.
- Add a real "Updated daily · last refresh 7:24 am" timestamp tied to data freshness.

### C13. A11y polish (shippable in one pass)

- Replace `role="list"` chips with `<ul role="list" class="chips">` (yes role=list is a no-op for `<ul>` but VoiceOver reads it more reliably) and `<li>` items.
- Add `:focus-visible` ring to `.card`, `.cat-tile`, `.chip`, `.composer input`, `.composer .send`.
- Visible label *Ask Hava* above the composer (not just placeholder).

---

## Part D — File-touch summary (for Cursor)

```
HIGH IMPACT (do these first)
  app/home/queries.py
    + CATEGORY_LABELS, CATEGORY_QUERIES dicts
    + _card_blurb helper (URL/newline scrub)
    + time-of-day-aware tonight()
    + real _hours_status (or return None when unknown)
    + use real human labels in top_categories()
  app/db/models.py
    + Event.summary nullable column (≤140 chars)
  app/templates/home.html
    + section labels read time-of-day
    + glyph SVGs replace circle dots
    + de-dup footer, add "updated at" line

PALETTE / COMPONENTS
  app/static/styles/home.css
    :root token replacement (see §B2)
    new card variants (editorial / listing / row item)
    place-cue divider class
    real status pill state machine
  app/static/styles/chat.css
    :root parity with home.css

NEW SURFACE
  app/home/category_router.py        (browse mode)
  app/templates/category.html
  app/static/js/home-composer.js     (progressive enhance)
  app/static/icons/categories/*.svg  (10 glyphs)
  app/static/img/hero/havasu-*.jpg   (hero photos)
  app/static/img/fallback/*.svg      (3 patterns until real photos)

MONETISATION (4 tiers, not 5)
  app/home/sponsor_store.py          (AdSlot enum: MARQUEE/SPOTLIGHT/PROMOTED/SUPPORTER)
  app/db/models.py                   (Sponsor model: slot, dates, copy, status FSM, metrics)
  app/templates/_partials/marquee.html       (Tier 1 — sold + unsold-shrunk states)
  app/templates/_partials/promoted_card.html (Tier 3 — clay left edge, Ad eyebrow)
  app/templates/_partials/supporters.html    (Tier 4 footer wall, max 4 logos)
  app/sponsor/router.py              (public rate-card + draft submit + click attrib)
  app/admin/sponsor_html.py          (review queue, inventory calendar, pause toggle)

PERF
  app/static/fonts/                  (self-hosted Inter + Fraunces)
  app/templates/base.html            (preload marquee photo, font-face declarations)

REMOVED
  .read CSS block in home.css
  read section in home.html
  hava_read context + builder in router.py / queries.py
  Section underwriter tier (dropped — was Tier 4 in earlier proposal)
  Weekly Hava tagline idea (dropped — page contracts at the old read slot)
```

## Part E — Definition of done

The redesign is shippable when every one of these is true:

1. No underscore-shaped string appears in any user-visible text on `/home`.
2. No card blurb contains `http`, `\n`, or an ISO date.
3. The section above *Hava's read* reads "Today" before 4 PM and "Tonight" after.
4. No two adjacent cards on `/home` show the same image surface.
5. Every interactive element shows a `:focus-visible` outline at ≥3:1 contrast.
6. `/home` Lighthouse a11y ≥95.
7. Hero composer submits without a full page navigation when JS is enabled, and still works without JS.
8. The page contains at least four distinct visual rhythms (no four-in-a-row identical card grids).
9. Every status pill is justified by data; no "Open · Hours on profile."
10. `/categories/{slug}` exists and renders a filterable list; clicking a category tile uses it.
11. The `read` CSS class and `hava_read` context key are gone from the codebase. The Marquee sits *below Today*, not below the hero.
12. Every paid surface has a visible disclosure using one of two words: `Ad` (Marquee, Promoted) or `Supporter` (Supporters wall). Spotlight retains its `Spotlight` badge as a card-level treatment. No euphemisms anywhere.
13. At most one `Promoted` card appears on the entire page (not per row).
14. Editorial cards have a 1px `--water` left edge with `--shadow-2`; same-row Promoted cards have a 3px `--clay` left edge with `--shadow-1`. The differentiator is visible side by side.
15. With zero sponsor records: Marquee renders as a single eyebrow + link line (not a CTA card), Spotlights/Promoted/Supporters all hide entirely, and the page still feels finished.
16. No `Sponsor` row with `status != approved` is ever served to `/home`. Pausing a live sponsor takes effect within 5 minutes (the cache window).
17. `/home` LCP ≤2.5s on simulated 4G mobile. Zero requests to `fonts.googleapis.com` or `fonts.gstatic.com`.
18. Card-blurb cleanup runs through `tier3_postprocess` for factual summarisation only. No AI-generated picks, opinions, or curatorial copy anywhere on `/home`.
19. The "faceless persona" audit passes: Hava brand references on `/home` are limited to the five touchpoints in §B5.8 (wordmark, hero H1, first-person voice in selected copy, "Hava's pick" badge, chat name). No humanoid figure (drawn, photographed, animated, or stylised) appears on the page. No copy uses banned Southwest climate language.

---

*Owner note:* nothing about the underlying chat architecture (`tier1/tier2/tier3` pipeline, `unified_router`, etc.) needs to change for any of this. The surface fixes are entirely in the home/templates/static layer plus the `queries.py` content cleaners. The chat tier code is well-structured; the visual layer is what's letting it down.
