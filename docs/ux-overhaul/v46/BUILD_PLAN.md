# v4.6 BUILD PLAN — polish trio, last pages, one shell

Live QA evidence behind this plan (2026-07-04 sweep of prod):
- Water tile still honest-omitted on /home — the RISE header fix is deployed and the
  gauge verified live (80.7°F), so the remaining gate is the feature flag / cron.
- Provider pages without their own description lead the About block with the
  auto-built disclaimer ("This listing is auto-built from trusted public data…").
- /movies showtimes render as underlined text links; home's movies section uses
  `.tpill` pills — inconsistent.
- Seven surfaces still extend `base_lake.html`: /today, /account, /contribute,
  /feedback, /portal/claim, admin pages, and the 404/error page.

---

## PR-0 · `feat/v46-00-polish` — three small fixes, shipped first

1. **Water tile default-on.** Find the flag gating the RISE water-temp source
   (v4.5 named it `FEATURE_FLAG_WATER_TEMP_RISE_6127` or similar — locate the real
   name in the conditions source). Flip the CODE DEFAULT to enabled; an explicit
   env var can still disable it. Keep the 6h window and honest-omit exactly as
   they are. Add a test: default-on when the env var is absent. Note in the PR
   body + PROGRESS: *if the tile is still omitted 24h after this deploys, the env
   var is explicitly set false in Railway — that single check is Casey's.*
2. **Provider About copy.** When a provider has no description of their own, the
   About body becomes the short factual line (name · category · address/area —
   whatever fields exist), and the "auto-built from trusted public data · suggest
   an edit" sentence moves to a small `.gasnote`-style footnote next to the
   suggest-an-edit control. Never as the About lead. Test: fixture provider
   without description → About does not start with "This listing is auto-built".
3. **Movies tpills.** /movies showtime links become `.tpill`-styled anchors
   (same booking hrefs, pill chrome, tabular-nums), matching home's movies rows.
   Keep them real links (they go to ticketing).

Acceptance: three tests + full gates. Merge before PR-1.

## PR-1 · `feat/v46-01-last-pages` — the final seven surfaces

Migrate off `base_lake.html`:
- **/today** (lake report) — discovery page: full v4 shell + cond strip. This is
  a content-rich page; reuse home/calendar components (serif heads, cards, `.tg`
  chips). Water/lake data follows honest-omit rules.
- **/account, /contribute, /feedback, /portal/claim** — utility pages: v4 shell +
  footer, no cond strip (v4.5 §Pre-answered 1). Forms restyle like /login did
  (v4.5 PR-5's auth pattern). Preserve every form action, field name, and JS hook.
- **404/error page(s)** — see Pre-answered 2.
- **Admin pages** — see Pre-answered 3.

Acceptance: each page 200 + `lake_redesign.css` + zero `base_lake` extends in
app templates (admin exception per Pre-answered 3); form posts still work
(existing tests); refs captured.

## PR-2 · `feat/v46-02-one-shell` — delete the old shell for good

After PR-1, grep-prove and delete: `base_lake.html`, `site_chrome.css`, and every
partial/stylesheet only they referenced (v4.5's kept list: lake_editorial.css,
lake_account.css, lake_landing.css, lake_portal.css — delete each one that PR-1's
migrations orphaned; keep any still linked by a live template). Extend the sweep
guard test: `base_lake.html` absent, `site_chrome.css` absent, zero references.
UX layer only; reference-search proof per deletion in the PR body.

Acceptance: guard tests; full gates; every public route still 200 (smoke list).

---

## §Pre-answered decisions

1. **/today content**: it's the "Lake report" — keep all its real data blocks,
   restyled; anything fabricated-looking (placeholder imagery, drawn art) is
   removed under DESIGN_SPEC §0. Water temp on /today follows the same source +
   honest-omit as the home tile.
2. **404/error**: create `base_plain.html` — v4 tokens, six-link header, footer,
   no cond strip, no JS beyond the shell — and point error handlers at a simple
   serif "Can't find that" page with a search box and a Today link. Keep status
   codes correct.
3. **Admin**: admin templates may extend `base_plain.html` (shell-only, no cond
   strip, no public nav actions) — the goal is deleting base_lake, not designing
   admin. If an admin page is genuinely easier left alone, it may NOT keep
   base_lake; base_plain is the floor. Function over polish here; do not spend
   more than the minimum to preserve behavior.
4. **Forms**: never change field names, actions, methods, or validation — chrome
   only. If a page has CSRF or session subtleties, test the POST path explicitly.
5. **/portal/claim**: the v4.5 sed over-reach already touched its test once —
   read that history (v45 PROGRESS) before editing; migrate deliberately.
6. **Flag semantics (PR-0.1)**: if the flag turns out to gate more than the RISE
   source (e.g., the whole water pipeline), still default it on — honest-omit
   protects the UI; log the finding.
7. **Anything uncovered**: v4.4 decision 15 — more real info, nothing fabricated,
   no new ad surfaces, smallest diff; log it, don't ask.

## Post-deploy smoke (final PR)

/home /gas /calendar /events-ui /categories /movies /today /account /feedback
/contribute → 200, v4 shell, zero emoji, Phoenix date where dated; 404 route
returns styled page with status 404; provider About fixture behavior spot-checked
on a live no-description provider if one exists.

## Stop conditions

Same three as always (migration/secrets/user-data deletion). Everything else:
resolve per contracts, log it, keep going.
