# OpenClaw → Facebook: Cron-Job Avenues for Lake Havasu (brainstorm)

The menu of "feeds" OpenClaw could pull from Facebook into your site, what each
gives users, where it comes from, and the two things that shape feasibility:
**access** (public Page = safe via Oxylabs, no login / private Group = needs your
login, account risk) and **content type** (text vs. image — most FB promo is
*image flyers*, which is why the Claude-vision path matters).

Legend: 🟢 public Page (safe) · 🔒 private Group (your login) · 🖼️ image-heavy (needs vision) · 🔤 mostly text

---

## Tier 1 — highest value, do first

**1. Bars / restaurants / breweries — happy hours, daily specials, live music** 🟢 🖼️
- Source: each venue's public Business Page (your candidate list + discovery).
- Pull: happy-hour times, daily specials (taco Tuesday…), live-music nights, one-off events.
- Lands as: Offerings + Schedules (ongoing deals) and Events (dated).
- Cadence: weekly per venue, paced.

**2. Local events feeds** 🟢/🔒 🖼️
- Sources: "Lake Havasu City Official Events Page" (group), Havasu Events, plus
  golakehavasu.com & downtownlakehavasu.com (public, already partly covered).
- Pull: concerts, festivals, markets, fundraisers, themed nights.
- Lands as: Events. Cadence: every 1–2 days (events are time-sensitive).

**3. Live-music / entertainment venues** 🟢 🖼️
- Sources: Flying X Saloon, BabaLoo Lounge, The Office, Grace Arts Live, BJ's Cabana.
- Pull: show calendars, ticketed events, karaoke/trivia nights.
- Lands as: recurring Events. Cadence: weekly.

---

## Tier 2 — strong community value

**4. Orchids & Onions (community praise / complaints)** 🔒 🔤
- Source: the Orchids & Onions group (private — needs your login).
- Pull: praise (orchids → public, moderated) and complaints (onions → internal only).
- Lands as: the new community-mentions model. Cadence: a few times/week.

**5. City / civic / parks & rec / library / Chamber** 🟢 🖼️/🔤
- Sources: City of Lake Havasu City, Parks & Rec, Library, Chamber of Commerce pages.
- Pull: public meetings, programs, closures, seasonal activities. (You already have a civic scraper to build on.)
- Lands as: Events / announcements. Cadence: weekly.

**6. Markets, food trucks & pop-ups** 🟢/🔒 🖼️
- Sources: farmers-market pages, food-truck pages, seasonal pop-up organizers.
- Pull: where/when this week. Lands as: recurring Events + Offerings. Cadence: weekly.

**7. Gyms / fitness / yoga studios** 🟢 🖼️
- Sources: your fitness list (Eight Lotus, FitLab, Fiore's, etc.).
- Pull: class specials, challenges, community events, new-member deals.
- Lands as: Programs / Offerings / Events. Cadence: every 1–2 weeks.

---

## Tier 3 — niche / optional (decide later)

**8. Big seasonal festivals** 🟢 🖼️ — Balloon Festival, Bluegrass on the Beach, Rockabilly Reunion, boat shows. High-value but infrequent; a slow monthly sweep catches them.

**9. Yard / garage / estate sales** 🔒 🔤 — very active groups (Havasu's Online Yard Sale, Garage & Estate Sale Announcements). Time-sensitive, high volume, lower "directory" fit. Could be its own dated "this weekend" feed if you want it.

**10. Retail deals / coupons / limited-time offers** 🟢 🖼️ — shops & services beyond food. Lands as Offerings.

**11. (Probably skip for the directory):** Marketplace buy/sell/trade, lost-&-found pets, real estate/open houses — high noise, weak fit for an events/places site.

---

## Cross-cutting recommendations

- **Vision first.** Tiers 1–3 are mostly 🖼️ image flyers. Plan the pipeline around
  *capture image → Claude vision → extract → queue*, not text-only DeepSeek.
- **Public before private.** Start with all the 🟢 Page-based avenues (no login, no
  account risk). Tackle 🔒 groups (events page, Orchids & Onions, yard sales)
  deliberately later with the safer-login plan.
- **One cron per avenue, staggered.** Each avenue = its own paced cron so they don't
  collide and you can tune/disable individually. Time-sensitive feeds (events,
  markets) run daily; venue happy-hours weekly; festivals monthly.
- **Everything lands as pending** in your review queue — the human/Claude review gate
  stays the safeguard against bad extractions.

## Suggested first 3 crons (once vision is wired)
1. **Venue happy-hours/specials** (Tier 1 #1) — weekly, public Pages.
2. **Events feed** (Tier 1 #2) — daily, public sources first.
3. **Live-music calendars** (Tier 1 #3) — weekly, public Pages.
Then layer in civic, markets, fitness, and the private-group feeds.
