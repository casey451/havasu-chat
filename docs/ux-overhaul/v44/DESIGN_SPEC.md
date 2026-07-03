# v4.4 DESIGN SPEC — exact deltas on the live v4

Visual source of truth: the approved v4.4 mock (`ask-hava-premium-v4.4.html`; screenshots
verified 2026-07-02 with headless Chromium). Everything below is expressed as diffs on
`app/templates/home_redesign.html`, `base_redesign.html`, `_partials/*`, and
`app/static/styles/lake_redesign.css`. Tokens are UNCHANGED — the entire `:root` block
stays byte-identical. If a rule below already exists in lake_redesign.css, don't
duplicate it.

## §0 Guardrails (the feedback log as law)

1. The full day schedule is the product — never demote, never curate it away.
2. Collapsible category groups + nested sub-trees stay exactly as structured.
3. No drawn scene graphics, no emoji glyphs. Monoline stroke icons only.
4. Paid units: at most ONE rendering per page, first screen, clearly labeled,
   never disguised as a recommendation, never duplicated, never an empty-box wall.
5. Gas is a glance + one tap. Aligned tabular columns, never uneven chips.
6. No recommendation surfaces ("top rated", "where to eat tonight") — ever.
7. Evolve v4's language; do not restyle it. Cream `--paper`, teal `--teal`, brass
   `--brass`, Fraunces values / Inter UI, `--rad:18px`.
8. Honest data with honest clocks; when data is missing, omit the element.

## §1 Conditions strip (PR-4)

Order: Temp · Water · Wind · UV · Sunset · Gas. Clouds retired.

Template (`base_redesign.html` cond loop): no structural change — backend adds
`water` and `sunset` tiles to `cond_tiles` and drops `clouds` (contract §3).
Water tile carries `is_water: true` → class `water`; sunset value is `"7:48"` with
`unit: "pm"`.

CSS add:
```css
.cond .c.water{background:linear-gradient(180deg,rgba(231,240,240,.6),transparent)}
.cond .c.water .lab{color:var(--teal)}
```

Mobile (≤980 in production media queries): labels 8px letter-spacing .04em, values
15px, icons hidden in labels — mirror the mock's `.device.mobile .cond` rules into
the existing mobile media query.

## §2 Marquee (PR-5)

Sold state (template branch exists): eyebrow `Sponsored · {sponsor name}`, Fraunces
h3 hook, pitch ≤ 46ch, white CTA pill. ADD the brass keyline + the creative plate slot:

```css
.feature-marquee{box-shadow:0 14px 40px rgba(8,63,68,.30),inset 0 0 0 1px rgba(201,161,74,.26)}
.feature-marquee:hover{box-shadow:0 22px 56px rgba(8,63,68,.42),inset 0 0 0 1px rgba(201,161,74,.4)}
.feature-marquee .creative{flex:0 0 auto;width:138px;height:110px;border-radius:14px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:10px;background:linear-gradient(180deg,#fdf9ee,#f5ecd6);box-shadow:inset 0 0 0 1px rgba(154,118,37,.38),inset 0 0 0 4px #fdf9ee,inset 0 0 0 5px rgba(154,118,37,.24),0 6px 18px rgba(0,0,0,.25)}
.feature-marquee .creative .mono{font-family:var(--disp);font-weight:600;font-size:14.5px;color:#3c3110;letter-spacing:.01em;text-align:center;line-height:1.15}
.feature-marquee .creative .cl{font-size:7.5px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--brass)}
.feature-marquee .creative .rulet{width:28px;height:1px;background:linear-gradient(90deg,transparent,var(--brass-br),transparent)}
```

Creative plate content comes from sponsor fields (eyebrow-top / name / rule / eyebrow-
bottom); when the sponsor supplies a real logo image use it inside the same plate frame
instead of the typographic block. Hide the plate ≤430px (existing rule pattern).
Sold marquee keeps `::before` sheen DISABLED (existing `.sold` rule).

## §3 Retire placeholder ads (PR-5)

In `home_redesign.html`: delete the two `{{ ad_placeholder() }}` calls in the rail and
the `{% if loop.index % 2 == 0 …%}{{ ad_placeholder(infeed=True) }}` in-feed branch.
Keep the `ad_placeholder` macro itself (sponsor/portal pages may use it).
Keep `sponsor_slot(promoted)` OUT of the rail — if a promoted sponsor exists it does
NOT render on home (one paid unit rule); leave the data plumbed for category pages.

## §4 Rail (PR-5)

Desktop grid stays `1fr 320px`. Rail = two cards, sticky as today.

### §4.1 Find-any-business launcher
```html
<div class="railcard">
  <div class="rc-hd">
    <div class="rt serif">Find any business</div>
    <div class="rs">{{ directory_total }}+ real local listings · open-now first</div>
  </div>
  <form class="minisearch" role="search" action="/categories" method="get">
    <span class="mag">{{ icon('search', 14) }}</span>
    <input type="search" name="q" placeholder="Plumber, tacos, boat detail…" aria-label="Search the directory">
  </form>
  <div class="dirgrid">…8 .dirit rows…</div>
  <a class="rc-ft" href="/categories">All 16 categories {{ icon('arrow', 14) }}</a>
</div>
```
The 8 categories + short labels (exact, they truncate otherwise): Eat & Drink,
Home Services, Auto & Boat, **Health**, Shopping, **Salons**, Lake & Boating,
**Lodging** — each with live counts, links to its category page.

```css
.railcard{background:var(--surface);border:1px solid var(--hair);border-radius:var(--rad);box-shadow:var(--sh-sm);overflow:hidden}
.rc-hd{padding:14px 16px 4px}
.rc-hd .rt{font-family:var(--disp);font-weight:500;font-size:16.5px;letter-spacing:-.01em}
.rc-hd .rs{font-size:11.5px;color:var(--ink3);margin-top:3px;line-height:1.4}
.minisearch{display:flex;align-items:center;gap:8px;margin:11px 16px 0;background:var(--paper2);border:1px solid var(--hair);border-radius:10px;padding:0 11px;height:40px;transition:.2s}
.minisearch:focus-within{background:#fff;border-color:var(--teal-line);box-shadow:0 0 0 3px rgba(12,90,96,.07)}
.minisearch input{flex:1;border:0;outline:0;background:transparent;font-family:var(--ui);font-size:12.5px;color:var(--ink);min-width:0}
.dirgrid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--hair2);margin-top:12px;border-top:1px solid var(--hair2)}
.dirit{display:flex;align-items:center;gap:8px;padding:10px 11px;background:var(--surface);text-decoration:none;transition:background .15s;min-width:0}
.dirit:hover{background:var(--paper2)}
.dirit .ic{color:var(--teal)}
.dirit .dl{font-size:11.5px;font-weight:600;color:var(--ink2);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dirit .dc{margin-left:auto;font-size:10px;font-weight:700;color:var(--ink3)}
.rc-ft{display:flex;align-items:center;justify-content:center;gap:6px;font-size:12px;font-weight:600;color:var(--teal);padding:11px;border-top:1px solid var(--hair2);text-decoration:none}
.rc-ft:hover{background:var(--teal-soft)}
```

### §4.2 Local-news card
3 most recent stored items; serif 14px headline, `nr-region` chip (existing class) +
source · age meta; `All news →` footer. Class the card `newscard`.
```css
.newsit{display:flex;flex-direction:column;gap:3px;padding:11px 16px;border-top:1px solid var(--hair2);text-decoration:none;transition:background .15s}
.newsit:hover{background:var(--paper2)}
.newsit .nh{font-family:var(--disp);font-weight:500;font-size:14px;letter-spacing:-.01em;color:var(--ink);line-height:1.3}
.newsit .nm{font-size:11px;color:var(--ink3)}
```
Desktop: hide the ticker (`.newsbar{display:none}` inside the ≥980 query), show card.
Mobile: show ticker, hide card (`.newscard{display:none}` in the mobile range) and let
the rail flow below sections (`.main` back to block; rail `margin-top:14px`).

## §5 Gas UI (PR-6)

### §5.1 Grade segment (shared component)
```css
.gseg{display:inline-flex;background:var(--paper2);border:1px solid var(--hair);border-radius:9px;padding:2px;gap:2px}
.gseg button{border:0;background:transparent;font-family:var(--ui);font-size:10.5px;font-weight:700;letter-spacing:.04em;color:var(--ink3);padding:5px 10px;border-radius:7px;cursor:pointer;transition:.15s}
.gseg button:hover{color:var(--ink)}
.gseg button.on{background:#fff;color:var(--teal-deep);box-shadow:var(--sh-sm)}
.gseg.lg{border-radius:11px;padding:3px}
.gseg.lg button{font-size:12.5px;padding:8px 16px;border-radius:8px}
```
Buttons: `Reg · Mid · Prem · Diesel` (panel, compact) / `Regular · Midgrade · Premium ·
Diesel` (page, `.lg`). `aria-pressed` on each; list container `aria-live="polite"`.

### §5.2 Home panel
`gphead` right side hosts the compact segment (the "Updated…" string moves to the
footer link: `All {{n}} stations · updated {{label}} →` → routes to /gas).
Tile echo while panel open: label gains `<span class="gl">` (` · Diesel`), value swaps
to that grade's cheapest; both revert on close.
```css
.cond .lab .gl{color:var(--brass);font-weight:700}
.cond .caret{transition:transform .25s}
.cond .c.gas[aria-expanded="true"] .caret{transform:rotate(180deg)}
```

### §5.3 /gas page (v4 shell)
Head `Gas prices · cheapest first` + right-aligned honest clock; `.gseg.lg`; table:
```css
.gashead{padding:20px 16px 4px;display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.gashead h1{font-family:var(--disp);font-weight:500;font-size:24px;letter-spacing:-.02em;margin:0}
.gashead .n{color:var(--ink3);font-size:13px;font-family:var(--ui);font-weight:500}
.gashead .upd{font-size:11px;font-weight:600;color:var(--ink3)}
.gsegwrap{padding:12px 16px 2px}
.gaslist{display:flex;flex-direction:column;margin:12px 16px 0;background:var(--surface);border:1px solid var(--hair);border-radius:var(--rad);box-shadow:var(--sh-sm);overflow:hidden}
.gaslist .gasrow:first-child{border-top:0}
.gasrow.lg{padding:12px 16px}
.gasrow.lg .gr{font-size:17px;width:66px}
.gasrow.lg .gn{font-size:13.5px}
.gasrow.lg .gs{font-size:11.5px}
.chp{display:inline-block;font-size:8.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#5a4510;background:var(--brass-soft);border:1px solid var(--brass-line);border-radius:5px;padding:2px 6px;margin-left:8px;vertical-align:1px}
.gasnote{margin:10px 16px 0;font-size:11px;color:var(--ink3)}
```
Row = price (serif, `.gr`) · name (+ brass `Cheapest` chip on row 1) · address ·
`Directions ›`. Footnote: "Prices refresh through the day — the clock above is honest.
Stations without a grade simply drop off that view." Strip's gas tile on THIS page is
a plain span (no caret, no panel). Mobile: h1 20px, `.gseg.lg button` 11.5px/7px 10px.

## §6 Schedule niceties (PR-7)

### §6.1 Movies rows
Title-first (no `.evt` span at all), theater in `.em`, then:
```css
.tpill{font-variant-numeric:tabular-nums}  /* .times/.tpill already exist in lake_redesign.css */
.ev:hover .tpill{border-color:var(--teal-line)}
```
`showall` link unchanged.

### §6.2 Closed-section previews (`.sp`)
`.sp` styles exist. Emit server-side, from the section's own first rows:
```jinja
{%- macro sec_preview(s) -%}
  {%- set bits = [] -%}
  {%- for row in s.preview_rows[:3] -%}
    {%- set _ = bits.append(row.title ~ (' ' ~ row.time_short if row.time_short else '')) -%}
  {%- endfor -%}
  {%- if s.count > 3 -%}{%- set _ = bits.append((s.count - 3) ~ ' more') -%}{%- endif -%}
  {{ bits | join(' · ') }}
{%- endmacro -%}
```
Place between `.sc` and `.cv` in the summary. Cap ~60 chars (`max-width:44%` CSS
handles overflow). Hidden when open + on mobile:
```css
.sechd .sp{max-width:44%}
.sec[open] .sechd .sp{display:none}
/* mobile query: */ .sechd .sp{display:none}
.sec:not([open]) .sechd .cv{margin-left:0}
.sec[open] .sechd .cv{margin-left:auto}
/* mobile query: */ .sechd .cv{margin-left:auto}
```

### §6.3 Places pills (Kids/Seniors)
Append to the counts row (`.cpill.places` exists in production CSS): icon + label,
no count badge, links `/family` and `/seniors`. Icons: `kid` (head+shoulders),
`people` (two figures) — add to `redesign_icons.html` as monoline strokes (16-box,
1.4 stroke, round caps; geometry in the mock's sprite).

### §6.4 Date-strip activity (dots + spark)
```css
.dcard .act{display:flex;gap:3px;align-items:center;height:6px;margin-top:1px}
.dcard .act i{width:4px;height:4px;border-radius:50%;background:var(--teal-br);opacity:.5;display:block}
.dcard .act .ic{color:var(--brass-br)}
.dcard.on .act i{background:#cfe7e8;opacity:.8}
.dcard.wknd{background:linear-gradient(180deg,#fbfaf6,var(--surface))}
```
Markup per card: `<span class="act">` with 1–3 `<i>` per thresholds, or the spark icon
(10px) with `title` = headliner text on configured dates. `wknd` class on Sat/Sun.
aria-label additions: `— busy day` / `— quiet day` / the headliner text.

## §7 Shell (PR-8)

Nav links: Today · Events · Lake · Eat & Drink · Explore · For Business.
Mobile drawer keeps the FULL destination list (incl. News, Movies, Calendar, Gas,
For Kids, For Seniors). Footer: one shared partial; `For Business` + `Advertise`
carry `class="biz"`:
```css
.foot .fl a.biz{color:var(--brass-br);font-weight:600}
```
Email everywhere: `hello@askhava.com`. Trust line verbatim (§0.8 of README).

## §8 Icons (any PR that needs them)

New monoline glyphs to add to `redesign_icons.html`: `wave`, `sunset`, `people`,
`kid`, `fork`, `wrench`, `car`, `health`, `bag`, `scissors`, `anchor`, `bed`.
All: 16×16 viewBox, stroke `currentColor` 1.3–1.5, round caps/joins, no fills except
tiny dots. Exact path data is in the approved mock's sprite — copy it verbatim.

## §9 A11y + motion (all PRs)

- Focus-visible ring pattern already in production — extend the selector list to the
  new interactive classes (`.dirit`, `.newsit`, `.rc-ft`, `.gasall`, `.gseg button`).
- `prefers-reduced-motion`: no new animations beyond existing `rise`; the gas panel
  uses the existing grid-rows transition (CLS-safe).
- Gas list containers `aria-live="polite"`; segment buttons `aria-pressed`.
- Sticky header behavior unchanged (constant height + shadow only).

## §10 Perf notes (verified in the mock render)

No new libraries, no images added, icons are one inline sprite, grade switching is
~2KB of delegated vanilla JS, server renders the Regular view so JS remains optional.
Fonts stay self-hosted (production) — the mock's Google Fonts link is mock-only.
