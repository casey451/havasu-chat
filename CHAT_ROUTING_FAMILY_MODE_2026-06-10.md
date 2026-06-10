# Chat routing, family coverage & calendar Family Mode — 2026-06-10

Branch: `feat/chat-routing-family-mode`. Everything below ships in this branch;
nothing touches prod data (the one data change is a dry-run-gated seed script).

## 1. Chat → page hand-off ("I need a dog groomer" → the grooming page)

- `app/categories/leaf_query.py` — new `match_leaf_for_chat()`: strips
  listing-shaped leads ("i need a", "looking for", "find me a", …) before the
  same conservative exact-dict leaf lookup. Queries with factual/temporal
  payload (hours, phone, "open now", "tonight") never match — Tier 1 keeps
  those inline, exactly the split you described (phone number / open time
  stays in chat). Added singular synonyms (dog groomer, vet, pet store, …).
- `app/chat/unified_router.py` — `_leaf_page_handoff()` runs after Tier 1:
  short voice line + new `page_link` component (tier logged as `leaf_link`).
- `app/static/js/chat-new.js` + `desert_chat.css` — `page_link` renders as a
  prominent card linking to the category page.
- `GET /chat?q=…` page loads also benefit (same dict feeds the existing 302).

## 2. Chat formatting

- Long answers render clamped to 4 lines with a **Show more / Show less**
  toggle (`voice-clamp` in chat-new.js + desert_chat.css) — no paragraph walls.
- Removed the vestigial full-screen loading overlay (P0-2): no more double
  loading state, popup answer, or forced 1.1s delay.
- Fixed the double-submit race (P0-5) with an inflight guard.
- Share now copies the answer text (the old `/chat?ref=` links were dead,
  P0-3); the write-only Save button is removed until a surface reads it (P0-4).
- Failed turns get a **Try again** button.
- Site-wide copy pass: every user-visible ` -- ` → ` — ` (~30 instances across
  17 templates + chat JS strings), `->` → `→` on /search, chat empty-state
  headline no longer claims "I'm your local", disclaimer is now "Always call
  to confirm hours.", removed mobile-keyboard-popping `autofocus`,
  "Showing N of N" suppressed when redundant, sessionStorage calls guarded
  for private browsing.

## 3. Kids/family chat coverage

- New `app/chat/family_fun.py`: "what is there for kids" (kid token + browse
  shape) now answers with a curated `business_list` of live family venues —
  arcade (The Spot), bowling (Havasu Lanes), trampoline park, aquatic center,
  parks, skate/roller venues, RC track — matched by Google category + name
  keyword against the standard visibility gate, bars/casinos excluded, up to
  8 items, with a foot link to Things to Do. Deterministic, zero LLM.

## 4. Missing listings (Desert Hawks RC, roller rink)

Root cause: neither exists in the catalog at all (no Provider row, no scrape
hit; the taxonomy also has no arcade/bowling/skate/rink/RC leaves — see
COVERAGE_GAP_AUDIT_2026-06-10.md for the wider discovery-gap picture).

- `scripts/seed_family_venues.py` — seeds **Desert Hawks RC Club** (SARA Park
  R/C complex, deserthawksrc.club, AMA #1545) and **Havasu Skates (SARA Park
  Roller Rink)** (7260 Sara Pkwy, havasuskates.com) as `draft + pending_review`
  rows. Dry-run by default; `--commit` requires your go-ahead per repo rules,
  then they appear in the admin approval queue. Once approved they surface in
  search, chat, and the family-fun answer automatically.
- Heads-up: "Havasu Skates" vs "Havasu Sk8 Club" may be two related operations
  at the same rink — worth a local eye before approving. Roller Palace
  (3539 McCulloch) shows in old directories; I left it out as likely defunct.

## 5. Calendar Family Mode

- `?family=1` on `/events-ui` with a visible **Family mode** switch (works
  across Today / Day / Week / Month; the toggle state survives every
  intra-page link). New `app/events/family_filter.py` keeps only occurrences
  that positively read kid/family (Open Swim, Free Family Swim, story time,
  youth/family tags, SpongeBob Youth Edition…) and vetoes adult markers
  (21+, wine/beer, "Adults", Sippin' with the Somm, senior programming).
  Aquatic Center in family mode = Open Swim + family events only.

## Verification

- `ruff check .` clean; new tests in `tests/test_chat_page_handoff.py`,
  `tests/test_family_filter.py`, `tests/test_family_fun.py` (24 passing with
  the existing leaf-query suite); full `pytest` run green before commit.

## Not done / follow-ups

- Taxonomy leaves for arcades/bowling/skating/RC (needs a category-row
  migration + discovery queries; ties into the §2 coverage-gap plan).
- Age-range filtering on the calendar beyond kid/not-kid: most events carry no
  structured age data (WebTrac programs bake "Ages 5–12" into description
  text). Needs ingest-side fields first.
- The chat `?ref=` share-replay idea, saved-answers surface, favicon set, and
  the rest of the UI audit P1/P2 items.
