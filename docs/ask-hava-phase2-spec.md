# Ask Hava — Phase 2 Spec: Admin Console + Business Ad-Purchase Portal

**Status:** draft for build · 2026-06-03 · follows the public Sandstone site (live).
Scope per `03_FINAL_BUILD_SPEC.md` §5. Build behind the CLAUDE.md gates; Stripe
keys are owner-configured, never in the repo.

---

## 0. What already exists (build on it, don't duplicate)

The admin console is **largely built** (`app/admin/*`, auth-gated):
- Catalog: `/admin/categories`, provider approval (`/admin/providers/pending`),
  duplicate merge (`/admin/providers/duplicates`), events edit.
- Moderation: contributions queue (`/admin/contributions`), mentioned-entities,
  feedback.
- Sponsors: inventory view (`admin_sponsors_inventory.html`), upgrade requests
  (`admin_upgrade_requests.html`), claims queue (`admin_claims_queue.html`).
- Analytics: `/admin/analytics`.

Backing schema already present: `Sponsor` (slot, status, starts_at/ends_at,
active, weight, approved_by, impressions, clicks — a draft→review→approved→live
FSM), `Provider.tier/verified/featured/featured_description/pending_review`,
`QueryLog`/`ChatLog`.

**So Phase 2 is mostly two net-new things:** a **demand dashboard** over the
query log, and the **self-serve business portal** with Stripe checkout.

---

## 1. Admin console — gaps to close (§5a)

1. **Demand dashboard** (`/admin/demand`) — the query-log view: top intents,
   categories/searches with **no provider to serve** (the acquisition list),
   volume trends, click/call/view roll-ups by surface. This is both an ops tool
   and the **sales deck** for the portal. Reads `QueryLog`/`ChatLog` +
   `record_event` rows. No new schema.
2. **Ad/sponsor management UI** — extend the existing inventory view into full
   FSM control: per-surface inventory (1 sponsored slot/category, 1 gas sponsor,
   homepage featured, event boosts), assign/approve sponsors, move
   draft→review→approved→live, set live windows, pause. Most of the FSM exists
   in `sponsor_store`; this is the admin UI over it.
3. **Roles/permissions** — staff vs. business-owner scopes (owners reach only
   their own listing/placements via the portal; staff reach everything).

## 2. Business portal — the revenue front door (§5b), net-new

Route group `/portal/*`, owner-auth-gated (reuse the magic-link auth).

1. **Claim** (`/portal/claim`) — verify ownership of a listing → unlocks the free
   enriched-profile editor (photos, hours, menu, links → `Provider` enrichment +
   `tier`/`verified`). Feeds the existing admin claims queue for the human gate.
2. **Buy advertising** (`/portal/advertise`) — a catalog of the labeled products,
   each showing **availability/scarcity** + price (scarcity is the pricing model):
   - Verified/Enriched Listing subscription (~$20–50/mo)
   - Category Sponsorship — *"1 of 1 slots available for Eat & Drink"* (~$75–250/mo)
   - Homepage / Mode Featured card (~$150–400/mo)
   - Event boost (~$25–100/event)
   - Gas / utility sponsor — *1 exclusive* (~$100–300/mo)
   Sold-out surfaces show a **waitlist**, never a second slot.
3. **Checkout** (`/portal/checkout`) — **Stripe hosted checkout** (Checkout
   Session / Payment Links). **Security:** never store raw card data; keys in
   env/secrets only; verify the webhook signature; the owner configures live
   keys, not the build. On `checkout.session.completed` → create the `Sponsor`
   row in `draft`/`review` for the staff approval gate (no auto-go-live).
4. **Self-serve dashboard** (`/portal`) — active placements, simple performance
   (views/calls/clicks from `Sponsor.impressions/clicks` + `record_event`),
   renewals, upload creative. Clearly labeled, no dark patterns.

**Inventory enforcement:** the portal respects ad-load caps (≤1 sponsored slot
per category, 1 gas sponsor, etc.) — enforced server-side against
`sponsor_store` live filters. **Lead-gen stays deferred** until `query_log`
demand data justifies pricing; design the portal so it can be added as a product.

---

## 3. Build order (gated; each a PR, tests green, held/merged per owner)

1. **Demand dashboard** (admin, read-only over query log) — lowest risk, high
   value (it's the sales deck). **← start here.**
2. **Ad/sponsor FSM management UI** (admin) over the existing `sponsor_store`.
3. **Portal: claim + enriched-profile editor** (no payments yet).
4. **Portal: advertise catalog + scarcity display** (read-only inventory).
5. **Portal: Stripe hosted checkout + webhook → Sponsor draft** (owner wires keys).
6. **Portal: self-serve dashboard + renewals.**
7. **Roles/permissions** hardening across admin/portal.

## 4. Open product decisions (flag — do not guess)
- Final pricing per product (the ranges above are from the monetization model).
- Stripe vs. another processor; subscription vs. one-time per product.
- Whether claim verification is manual (admin gate) only, or adds an automated
  signal (email-domain / phone match).
- Reviews doctrine + compliant gas-data source still open (unchanged from blueprint).
