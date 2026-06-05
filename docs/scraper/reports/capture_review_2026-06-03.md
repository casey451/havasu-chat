# Capture review — 2026-06-03 (inbox: 6 captures, 0 flagged rows)

Vision-read per COWORK_REVIEW_RUNBOOK.md. Nothing was published; statuses flipped
as noted. Headline: **every capture hits Facebook's logged-out login wall after
~1 post**, so each yields page identity + contact + first/pinned post only. Per
the no-login architecture rule this is the expected ceiling; noted implications
at the end.

## 1. Anytime Fitness — `9fcb83d6-ffc5-4f24-94e8-7e573901b030` (lhc-schedule-sweep)
[Screenshot](https://pub-1d8bb46fee36476ea805a359082f8ab1.r2.dev/scrape-captures/a7ae7334-15f1-4483-95f8-b43b1663a7de.png)
Identity confirmed ("Havasu Anytime Fitness", 62 Lake Havasu Ave S, 6.2K followers).
Read: one partial post (#GlobalRunningDay community photos). Sidebar: phone (928)
302-3883, "Always open", 96% recommend. **No class times anywhere.**
Proposed record: none. Confidence: n/a. **Recommendation: skip** → marked reviewed.

## 2. Iron Age Gym — `a12929a9-8af8-427c-b5ab-ef03bc6d6f28` (lhc-schedule-sweep)
[Screenshot](https://pub-1d8bb46fee36476ea805a359082f8ab1.r2.dev/scrape-captures/31596854-086f-4350-94cc-29b7f4fbbcf8.png)
Identity confirmed (Iron Age Gym, 1880 Commander Dr, only 72 followers).
Read: one post (Nov 3, 2025 — new equipment announcement). No schedule content.
Page is low-activity; their Gymdesk portal (already captured in the website crawl)
is the better source. Proposed record: none. **Recommendation: skip** → reviewed.

## 3. "Mudshark Brewery" — `426ee13d-1316-4350-8543-9bf0e112bdd2` (bars batch1) — **MISLABELED**
[Screenshot](https://pub-1d8bb46fee36476ea805a359082f8ab1.r2.dev/scrape-captures/f1a91d5d-6b46-427e-a6b1-4b35cac96fa6.png)
The page is actually **Flying X Saloon** (URL was right, the DeepSeek-supplied
business_name was wrong). Identity clean: 2030 McCulloch Blvd N, (928) 854-3599,
flyingxsaloon.com, Bar & Grill, 92%/2,196 reviews, 12K followers.
Read: post "See ya guys TONIGHT!" + shared Tru Phonic post: "LAKE HAVASU CITY this
Wednesday 7pm at @flying_x_saloon_havasu". Photos grid shows a chalkboard
"MONDAY BEER DOD $6" (thumbnail, low certainty).
Proposed records:
- Event (live music): Tru Phonic at Flying X Saloon — Wed 2026-06-03, 7:00 PM,
  source_url facebook.com/FlyingXSaloon. Confidence: medium-high.
- Offering+Schedule (candidate): "Monday Beer of the Day $6" — days_of_week Mon,
  price_text $6. Confidence: LOW (read from photo thumbnail only).
**Recommendation: needs Casey** (fix business_name → Flying X Saloon; confirm the
Monday beer special before ingest) → left as `new`.

## 4. "Shugrue's Restaurant & Bar" — `78b3cdfb-40d6-4b34-aff3-abbd85d0bfba` (bars batch1) — **MISLABELED**
[Screenshot](https://pub-1d8bb46fee36476ea805a359082f8ab1.r2.dev/scrape-captures/d20656b6-b9ca-4dea-8544-0adee58cb08d.png)
The page is actually **The Office Cocktail Lounge & Grill** (URL right, label wrong).
Identity clean: 2180 Acoma Blvd W, (928) 855-9583, officebar@yahoo.com,
Officebarhavasu.com, Sports Bar, 90%/1,147 reviews.
Read (verbatim intro): "We are open 365 days a year at 9 AM until 2 AM! Every
night we have an event going on!" Plus a May 8 post (staff video, 116 likes) and
a "GYPSY WAGON BAND" poster thumbnail (recurring live music signal).
Proposed records:
- Entity Hours: daily 9:00 AM–2:00 AM, 365 days. Confidence: high (verbatim).
- Note for events pipeline: "event every night" claim + Gypsy Wagon Band —
  needs a follow-up source for specific days/times.
**Recommendation: needs Casey** (fix business_name → The Office Cocktail Lounge &
Grill; approve hours ingest) → left as `new`.

## 5. Barley Brothers — `5fdea5a2-fe5e-462b-90c6-857123533811` (bars batch1)
[Screenshot](https://pub-1d8bb46fee36476ea805a359082f8ab1.r2.dev/scrape-captures/ecc149cb-a789-4a8b-ae8d-70ee32f836e7.png)
Identity confirmed (1425 McCulloch Blvd N, (928) 505-7837, 94%/2,999 reviews).
Read: one truncated post (May 22, "Serving Lake Havasu City…"); a "PIZZA & PINT"
promo thumbnail (no day/time/price legible). No ingestable deal/event text.
Proposed record: none (Pizza & Pint = lead for a future pass).
**Recommendation: skip** → reviewed.

## 6. College Street Brewhouse — `51b84a46-5a10-4a3c-811f-343aa3147c62` (bars batch1)
[Screenshot](https://pub-1d8bb46fee36476ea805a359082f8ab1.r2.dev/scrape-captures/546ef357-06bc-4e77-b08c-d9738cb9dbee.png)
Identity confirmed (2145 College Dr, (928) 854-1236, brewery since 2011).
Read: one fully legible post (May 23): Tim's retirement party, Fri May 29, 3 PM —
already past and a one-off, not pipeline material. No deals/recurring events visible.
Proposed record: none. **Recommendation: skip** → reviewed.

## Problems for Cowork/Casey
- No flagged (metadata-only) rows in the queue.
- **2 of 6 captures had wrong business_name** (DeepSeek paired wrong names with
  right URLs during the old bars run): #426ee13d should be Flying X Saloon,
  #78b3cdfb should be The Office Cocktail Lounge & Grill. The ingest API has no
  rename endpoint — fix in admin or note for the Jobs-page build.
- **Login wall ceiling**: all 6 captures gated after ~1 post. With the no-login
  rule, FB yields ≈ identity + pinned/first post + intro + photo thumbnails.
  Suggestion: treat FB captures as a *verification + first-post* source, and
  lean on websites (deep-crawl pass is now strong) for schedules.
- Bars sweep apparently completed Flying X + The Office (mislabeled) before
  disable; Javelina Cantina was never captured.

## Quality tally
Legible: 6/6 (all partial — login wall). Identity confirmed: 6/6.
Useful structured data: 2/6 (33%) — Flying X (event + candidate deal), The Office
(hours). Mislabeled metadata: 2/6. Statuses: 4 → reviewed, 2 left `new` for Casey.
