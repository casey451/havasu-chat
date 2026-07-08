# WS12 — Coverage Connectors: Credential & Access Checklist

**For:** Casey — everything to gather in one sitting before WS12 (the coverage
connectors, spec §12) is built.
**Status:** planning only. No connector is built yet; nothing here writes to prod.
**Prepared:** 2026-07-08 (end of the WS10 hub session).

WS12 is the moat: seven connectors that widen event/venue coverage. Each one goes
through the **same downstream pipeline** — normalize → WS5 series model → WS4
venue match → WS6 classifier → **review queue** (low-confidence) → publish → WS1
purge. **No connector writes to prod directly.** So the only thing that gates the
build is *access* to each source. This doc is that access list.

The connectors, in the spec's priority order:

| # | Connector | Source | Access type | Casey action needed | Effort |
|---|---|---|---|---|---|
| C1 | **Facebook Pages** | ~50-page watchlist (below) | ⚠️ **Decision required** (see §1) | Choose the FB access path | High |
| — | **Split Finger directory entry** | (not a connector — a single listing) | None | Approve the row (§2) | Trivial |
| C2 | **Trumba** | Mohave County Library – Havasu storytimes | Public JSON (likely no key) | Confirm the embed/library page URL | Low |
| C4 | **azstateparks** | Lake Havasu State Park events | Public page / possible iCal | Confirm no login needed | Low |
| C3 | **GrowthZone / ChamberMaster** | Lake Havasu Area Chamber calendar | Public calendar; **API key optional** | Decide scrape vs. ask Chamber for API access | Medium |
| C5 | **Squarespace** | Havasu Museum of History events | Public JSON (Squarespace `?format=json`) | Confirm the site URL | Low |
| C6 | **MyRacePass** | Havasu 95 Speedway schedule | Public schedule; **API key optional** | Decide scrape vs. request MRP API key | Low–Med |
| C7 | **Venue-watcher** | Dynamix `/summer-camp-2026`, Wix booking pages | Public page-diff (no creds) | Provide the venue URL list | Low |

---

## 1. Facebook Pages (C1) — the one real decision

Facebook is the **highest-yield** connector (it closes the two client-named gaps
at once: Altitude's camps/Glow nights and Barley Brothers' happy hour + live
music) and the **hardest to access**. There is no free, ToS-clean way to read
~50 pages you don't own. Pick one path with eyes open:

### The exact page watchlist (spec §12)
Confirm the current handle/URL for each — some are handles, some are business
names to look up. Check each box once you've confirmed the page exists and is
public:

- [ ] **Altitude Lake Havasu** — `facebook.com/altitudelakehavasu` (ALOHA camps, Glow nights) — *client-named gap*
- [ ] **Split Finger Athletics** — page (SARA Park cages, clinics, camps) — *client-named gap*
- [ ] **Barley Brothers** — `facebook.com/BarleyBrothers` (happy hour M–F 3–6, live music) — *client-named gap*
- [ ] **College Street Brewhouse** — `facebook.com/CollegeStreet`
- [ ] **Flying X Saloon**
- [ ] **Kokomo** (Beach Club)
- [ ] **Lady Lee's** (Billiards Hall)
- [ ] **Calvary Baptist** (church)
- [ ] **Calvary Chapel LHC** (church)
- [ ] **Lake Havasu Baseball Academy** (SARA Park cages)
- [ ] **Grace Arts Live**
- [ ] **Havasu 95 Speedway** (also covered by MyRacePass, C6 — FB is the backup)

…plus room to grow the list toward ~50 (bars, churches, youth studios, venues).

### Access options & tradeoffs

**Option A — Meta Graph API with page access tokens (pages you or the owner control)**
- *What it is:* the official API. A Page access token reads that page's posts/events cleanly (structured JSON).
- *Requires:* you must be an **admin/editor of the page**, OR the page owner adds your Meta app and grants a token. Plus a Meta Developer app + a long-lived token.
- *Reality:* works for pages Casey controls or has a relationship with (maybe Altitude, Barley Brothers, a church). **Does not scale to 50 third-party pages** — you can't get admin on Kokomo's page.
- *Tradeoff:* cleanest + ToS-compliant, but coverage is limited to pages that opt in.

**Option B — Meta Graph API with *Page Public Content Access*** (read public pages you don't own)
- *What it is:* a special Graph API permission to read **any** public Page's content.
- *Requires:* a Meta app + **Business Verification** + **App Review** where Meta approves the "Page Public Content Access" feature. Weeks of lead time; Meta can reject; ongoing compliance.
- *Tradeoff:* the only *official* way to read all 50 pages — but a heavy, uncertain approval. **Start this early if you want it** (it's the long pole).

**Option C — Public scraping (no credentials)**
- *What it is:* fetch each public page and parse posts/events.
- *Reality:* violates Facebook's ToS; login walls + markup churn + aggressive bot-blocking make it fragile; risk of IP bans.
- *Tradeoff:* zero credentials, fastest to prototype, but brittle and against ToS. Not recommended as the durable path.

**Option D — a third-party FB data provider** (paid API that already has FB access)
- *What it is:* a vendor (e.g., a social-data API) that returns a page's posts.
- *Requires:* a paid account + API key.
- *Tradeoff:* offloads the FB access problem for a monthly cost; check each vendor's own ToS/legality.

**Recommendation to decide on:**
Do **A** for the handful of pages you have a relationship with (Altitude, Barley
Brothers, a church or two) — highest signal, lowest risk — **and** kick off **B**
(App Review) in parallel if you want full coverage, since it's the long pole. Treat
**C** as a stopgap only if you accept the ToS/fragility risk; **D** if you'd rather
pay to skip the FB access problem. **This is a Casey judgment call + spend
decision — flagged, not made here.**

> Whatever the path, the FB connector still runs post → LLM event extraction
> (date/time/title/price) with **WS6 confidence gating** → review queue. Low-cost
> either way once access exists.

**To gather for C1:** a Meta Developer account (developers.facebook.com), a Meta
**Business** account (business.facebook.com) if going the App-Review route, and a
list of which watchlist pages you can get admin/token access to vs. which need B/C/D.

---

## 2. Split Finger Athletics — do this now (not a connector)

Independent of any connector: **Split Finger is absent from the directory
entirely**, so `/search?q=batting cages` returns nothing (a named coverage gap).
Add the listing directly (no credentials needed — you have the facts):

- **Name:** Split Finger Athletics
- **Address:** 5601 Hwy 95, Bldg F, Ste 600, Lake Havasu City, AZ
- **Phone:** (928) 223-1504
- **Website:** splitfingerathletics.com
- **Category:** Fitness / Batting Cages **+** Kids' Classes & Camps

- [ ] Confirm these details are still current, then I can add the row via the
      gated data-op flow (dry-run → your approval → apply).

---

## 3. The other connectors (mostly public — low/no credential)

### C2 — Trumba (Mohave County Library – Havasu storytimes)
- **Source:** the library's events page carries a **Trumba** embed; Trumba serves
  the data as **JSON underneath the widget** (a "spud"/JSON endpoint).
- **Access:** typically **no key** for public calendars — the JSON is fetchable.
- **To gather:** the exact library-branch events page URL (mohavecountylibrary.us
  Lake Havasu branch) so the connector can find the Trumba `webName`/feed id.
- [ ] Confirm the library events page URL.

### C4 — azstateparks (Lake Havasu State Park)
- **Source:** azstateparks.com events (Bluegrass, Boat Show, campouts).
- **Access:** **public** — an events page and possibly an iCal/feed; **no login**.
- **To gather:** confirm the Lake Havasu State Park events URL and whether they
  publish an iCal (`.ics`) feed (preferred over scraping the page).
- [ ] Confirm URL / check for an `.ics` feed.

### C3 — GrowthZone / ChamberMaster (Lake Havasu Area Chamber)
- **Source:** the Chamber's events calendar (GrowthZone/ChamberMaster platform).
- **Access:** the **public calendar** is scrapeable; GrowthZone also has an
  **API that requires the Chamber's API key** (a member/partner credential).
- **Decision:** scrape the public calendar (no creds, fine to start) **or** ask
  the Chamber for GrowthZone API access (cleaner, but needs their cooperation).
- **To gather:** the Chamber calendar URL; and if you want the API, a contact at
  the Chamber to request a key.
- [ ] Decide scrape vs. API; get the calendar URL (+ Chamber contact if API).

### C5 — Squarespace (Havasu Museum of History)
- **Source:** the museum's Squarespace site events.
- **Access:** Squarespace exposes page data as **JSON by appending
  `?format=json`** to the events collection URL — **no key**.
- **To gather:** the museum's events page URL.
- [ ] Confirm the museum events URL.

### C6 — MyRacePass (Havasu 95 Speedway)
- **Source:** the Speedway's schedule on **MyRacePass**.
- **Access:** the **public schedule page** is readable; MyRacePass also offers an
  **API (key on request)** for tracks/partners.
- **Decision:** scrape the public schedule (fine to start) **or** request an MRP
  API key if you want structured data.
- **To gather:** the Speedway's MyRacePass URL; MRP API contact only if going API.
- [ ] Confirm the MyRacePass URL; decide scrape vs. API.

### C7 — Venue-watcher (page-diff, no credentials)
- **Source:** venues that have a website but no feed — hash their pages weekly and
  extract on change. Notable patterns: **Dynamix** `/summer-camp-2026` sub-pages,
  **Wix** booking pages.
- **Access:** **none** — just public page fetching.
- **To gather:** the list of venue URLs to watch (Dynamix, and any Wix-hosted
  studios/venues you want covered).
- [ ] Provide the venue URL watchlist.

---

## 4. One-sitting gather list (tl;dr)

**Decisions only you can make:**
- [ ] **Facebook access path** (A page-tokens / B App-Review / C scrape / D paid vendor) — the big one; start B early if you want it.
- [ ] GrowthZone: scrape vs. Chamber API key.
- [ ] MyRacePass: scrape vs. MRP API key.

**Accounts to create (only if going the API route on that source):**
- [ ] Meta Developer account (+ Meta Business account for FB Option A/B).
- [ ] (Optional) third-party FB data vendor account, if Option D.
- [ ] (Optional) GrowthZone API key via the Chamber; MyRacePass API key via MRP.

**URLs / facts to confirm (public, no creds):**
- [ ] The 12 seed FB pages above (handles/URLs, public).
- [ ] Split Finger details (§2) — for the immediate directory add.
- [ ] Library Trumba events URL (C2).
- [ ] Lake Havasu State Park events URL / `.ics` (C4).
- [ ] Chamber calendar URL (C3).
- [ ] Havasu Museum of History events URL (C5).
- [ ] Havasu 95 Speedway MyRacePass URL (C6).
- [ ] Dynamix + Wix venue URLs to watch (C7).

**No credentials needed to start:** C2, C4, C5, C7, and the Split Finger add —
these can be built as soon as the URLs are confirmed. **C1 (Facebook) is the only
hard gate**, and it's an access/spend decision, not a build problem.
