# Human / infra checklist — scrape defense + SEO (the non-code half)

Companion to `SCRAPE_DEFENSE_AND_SEO_PLAN_2026-06-28.md`. These are the moves
Claude Code couldn't make — dashboards, prod data ops, off-page authority, legal.
Ordered by leverage.

> **Status (2026-06-29): the code half shipped.** All five PRs are merged to
> `main` and deployed:
> - #614 — A2 public-endpoint rate limits **+ B1** home tag-leak fix
> - #616 — A1 Cloudflare-ready rate-limit key (`CF-Connecting-IP`)
> - #617 — A4 canary listings + off-site copy detection (code only; **seeder not run** — see §2)
> - #618 — B2 `/categories` "Lake Havasu City directory" schema
> - #619 — A3 robots.txt + sitemap hardening *(originally #615; it auto-closed
>   when its stacked base branch was deleted on the #614 merge, so it was rebased
>   onto `main` and re-opened as #619)*
>
> Everything below is the remaining human/infra work.

---

## 1. Cloudflare — front the origin (biggest single scrape-defense lever; ~30 min)
Free tier covers all of this.
- [ ] Add askhava.com to Cloudflare and move DNS/proxy in front of Railway (orange-cloud the records).
- [ ] **Security → Bots →** turn on **Bot Fight Mode**.
- [ ] **Security → Bots →** toggle on **Block AI Scrapers and Crawlers** (one click; blocks GPTBot, ClaudeBot, CCBot, Bytespider, etc. + lookalikes).
- [ ] Add a WAF rule to **challenge datacenter-ASN traffic** to the directory/JSON paths (where real users shouldn't be coming from a cloud host).
- [ ] After Cloudflare is live, set **`TRUSTED_HOSTS`** in Railway (e.g. `askhava.com,*.askhava.com,*.up.railway.app`) — PR #616 made the limiter read `CF-Connecting-IP`, so per-IP limits now work correctly behind CF.
- [ ] Watch **Security → Events / Analytics** for a day to confirm you're not challenging Googlebot or real users; tune if needed.

## 2. Activate the canary system (PR #617 shipped the code; it's dormant until you run it)
Follow the repo's prod-data rule: **dry-run → show counts → approve → apply.**
- [ ] `python scripts/seed_canaries.py` (dry-run is the default) → review the counts/rows.
- [ ] Approve, then `python scripts/seed_canaries.py --apply` to seed the decoy listings (auto-excluded from counts + sitemap).
- [ ] Schedule `scripts/canary_scan.py` as a cron (e.g. daily) so you're alerted when a canary's unique string appears on havasu.info or anywhere off-site.
- [ ] Decide canary discoverability: they render at `/provider/<slug>` but aren't linked from listings. To bait an active scraper, link at least one from a low-visibility spot so a crawler can find it; keep it off high-traffic surfaces so real users don't hit it.

## 3. Off-page SEO / authority (the real lever vs an SEO agency; ongoing)
On-page parity is basically done — this is what decides the local SERP.
- [ ] **Google Business Profile** for Ask Hava — claim/verify, full categories, link to askhava.com. (Drives the entity + local pack.)
- [ ] **Local citations / inbound links** — get askhava.com listed/linked from: Lake Havasu Area Chamber of Commerce, havasunews.com, golakehavasu.com, the city site, and any "things to do in Havasu" roundups. A handful of relevant local links outweighs a keyword-match domain.
- [ ] **Bing Places** + Apple Business Connect while you're at it (cheap, broadens the entity footprint).
- [ ] Pick the one query that matters most (e.g. "lake havasu directory" / "things to do in lake havasu") and make sure the landing from PR #618 is the obvious best answer — then earn 2–3 links pointing at it specifically.

## 4. Legal — DMCA as copies appear (low effort, high impact on their ranking)
Your strongest claim is the **copied prior-version home-screen copy** (your git history proves you authored it first) + any copied photos/editorial. Facts (names/addresses/phones) aren't protectable.
- [ ] Assemble evidence: the matching passages (your git commit dates vs. their live page) + any canary hit.
- [ ] File with **Google's removal tool**: https://reportcontent.google.com/forms/dmca_search — this can delist the specific infringing URLs from Search (directly dents their ranking).
- [ ] File with **havasu.info's hosting provider** (find via their host's abuse/DMCA contact).
- [ ] *Not legal advice — use an IP attorney for anything beyond a standard DMCA notice.*

## 5. Measure the real gap (do this first if you want to prioritize by data)
- [ ] **Google Search Console** — verify askhava.com, then check Performance for which queries/pages havasu.info actually out-ranks you on before chasing. (Earlier: for the generic "lake havasu directory" neither of you was top — the city/chamber/golakehavasu own it — so confirm where the real loss is.)
- [ ] If you have Ahrefs/Similarweb, pull havasu.info's referring domains — tells you whether their edge is on-page (now closed) or off-page (Track 3).

---

### Suggested sequence
1. ~~Merge the PRs~~ ✅ done. 2. Cloudflare + `TRUSTED_HOSTS` (same day). 3. Search Console verify (so you can measure). 4. Canary seed + scan cron. 5. GBP + citations (ongoing). 6. DMCA whenever you spot a copy.
