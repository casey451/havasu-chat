# Tier 3 grounding verification — 2026-04-19

Database-only checks (via `railway run`, no Anthropic/production chat calls) after the production Tier 3 reply that mentioned **Altitude Trampoline Park** ($19 / 90 min) and **Flips for Fun Gymnastics** (3–8pm weekdays).

---

## 1. Data grounding

**Command run:** SQLAlchemy one-liner against Railway-linked DB (same as requested):

```text
railway run .\.venv\Scripts\python.exe -c "from app.db.database import SessionLocal; from app.db.models import Provider, Program; s = SessionLocal(); p = s.query(Provider).filter(Provider.provider_name.ilike('%altitude%')).first(); print('=== Altitude provider ==='); print(f'name: {p.provider_name if p else None}'); print(f'hours: {p.hours if p else None}'); print(f'category: {p.category if p else None}'); altitude_programs = s.query(Program).filter(Program.provider_id == p.id).all() if p else []; print(f'=== Altitude programs ({len(altitude_programs)}) ==='); [print(f'  {pr.title} | cost: {pr.cost}') for pr in altitude_programs]; flips = s.query(Provider).filter(Provider.provider_name.ilike('%flips%')).first(); print(f'=== Flips provider ==='); print(f'name: {flips.provider_name if flips else None}'); print(f'hours: {flips.hours if flips else None}'); s.close()"
```

**Captured output** (Windows console may mangle Unicode dashes; DB uses normal punctuation):

```text
=== Altitude provider ===
name: Altitude Trampoline Park — Lake Havasu City
hours: Sun 11am–7pm | Mon 11am–7pm | Tue 10am–7pm | Wed 11am–7pm
Thu 10am–7pm | Fri 11am–8pm | Sat 9am–9pm
category: fitness
=== Altitude programs (4) ===
  Open Jump — 120 Minutes | cost: $24.00
  Monthly Membership — Unlimited | cost: $25.00
  Monthly Membership — Standard | cost: $15.00
  Open Jump — 90 Minutes | cost: $19.00
=== Flips provider ===
name: Flips for Fun Gymnastics
hours: Opens 3pm, closes 8pm (Mon–Fri)
```

### Key questions

| Question | Answer |
|----------|--------|
| Is **“Flips for Fun Gymnastics”** in our catalog? | **Yes.** `Provider.provider_name` is **Flips for Fun Gymnastics**. Not invented. |
| Is Altitude’s **$19 / 90‑minute** offering in program data? | **Yes.** Program **Open Jump — 90 Minutes** with **cost: $19.00** (title reflects duration). |
| Are **3–8pm weekdays** the actual Flips hours? | **Yes, semantically.** Stored: **Opens 3pm, closes 8pm (Mon–Fri)** — same window summarized as 3–8pm weekdays. |

**Conclusion:** For that production answer, the named venues, price/duration, and Flips hours align with **seeded provider/program rows**, not obvious hallucination.

---

## 2. Tier 3 context (`build_context_for_tier3`)

**Intent:** Same query as the production smoke test:

`what's a good place for my 6-year-old to burn off some energy?`

**Note on invocation:** The user’s inline `\"what's...\"` inside `python -c` is awkward in PowerShell. The check was run equivalently by setting `HC_QUERY` to that string and reading `os.environ['HC_QUERY']` inside `-c` (same `classify` → `build_context_for_tier3` flow).

**Intent result:**

```text
=== INTENT RESULT ===
mode: ask, sub_intent: OPEN_ENDED, entity: None
```

**Full context string** (what Tier 3 could ground on for that turn; line breaks preserved):

```text
Context — Lake Havasu catalog snapshot (programs and events may be partial):

Provider: Altitude Trampoline Park — Lake Havasu City
  category: fitness
  address: 5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  phone: (928) 436-8316
  website: altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/
  hours: Sun 11am–7pm | Mon 11am–7pm | Tue 10am–7pm | Wed 11am–7pm
Thu 10am–7pm | Fri 11am–8pm | Sat 9am–9pm
  Program: Open Jump — 120 Minutes | ages n/a | schedule 09:00-10:00 | cost: $24.00
  Program: Monthly Membership — Unlimited | ages n/a | schedule 09:00-10:00 | cost: $25.00 | note: 7 days/week, 120 minutes/day
  Program: Monthly Membership — Standard | ages n/a | schedule 09:00-10:00 | cost: $15.00 | note: 5 days/week, 90 minutes/day
  Program: Open Jump — 90 Minutes | ages n/a | schedule 09:00-10:00 | cost: $19.00 | note: Any open session during business hours

Provider: Aqua Beginnings
  category: swim
  address: Private heated outdoor pool (address at booking)
  website: aquabeginnings.com

Provider: Arevalo Academy
  category: martial_arts
  address: 3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
  phone: (928) 855-0505
  website: arevaloacademy.com

Provider: Arizona Coast Performing Arts (ACPA)
  category: dance
  address: 3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  phone: (928) 208-2273
  website: arizonacoastperformingarts.com
  Upcoming event: ACPA Annual Dance Showcase 2026 on 2026-05-15 at 18:00 — Lake Havasu City, AZ — see description for venue details.
  Upcoming event: ACPA Annual Dance Showcase 2026 on 2026-05-16 at 18:00 — Lake Havasu City, AZ — see description for venue details.
  Upcoming event: ACPA Annual Dance Showcase 2026 on 2026-05-17 at 18:00 — Lake Havasu City, AZ — see description for venue details.

Provider: Ballet Havasu
  category: dance
  address: 2735 Maricopa Ave (inside The Dance Center), Lake Havasu City, AZ 86406
  phone: (928) 412-8208
  website: ballethavasu.org

Provider: Bless This Nest LHC
  category: art
  address: 2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  phone: (928) 412-3718
  website: blessthisnestlhc.com

Provider: Bridge City Combat
  category: martial_arts
  address: 2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  phone: (928) 716-3009
  hours: Closes 9pm. Full weekly hours not confirmed.

Provider: Flips for Fun Gymnastics
  category: gymnastics
  address: 955 Kiowa Ave, Lake Havasu City, AZ 86404
  phone: (928) 566-8862
  website: fffhavasu.com
  hours: Opens 3pm, closes 8pm (Mon–Fri)

Provider: Footlite School of Dance
  category: dance
  address: 2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  phone: (928) 854-4328
  website: footliteschoolofdance.com
  hours: Mon–Thu 3–7pm during dance year
  Upcoming event: Footlite Annual Recital — "Dance Party in the USA!" on 2026-05-30 at 18:00 — Lake Havasu High School Performing Arts Center, 2675 Palo Verde Blvd S, Lake Havasu City, AZ 86403
  Upcoming event: Footlite Annual Recital — "Dance Party in the USA!" on 2026-06-01 at 18:00 — Lake Havasu High School Performing Arts Center, 2675 Palo Verde Blvd S, Lake Havasu City, AZ 86403

Provider: Grace Arts Live
  category: theatre
  address: 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  website: graceartslive.com
  Upcoming event: Alice in Wonderland Jr. — Storybook Theatre 2026 on 2026-06-26 at 19:30 — Grace Arts Live, 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  Upcoming event: Alice in Wonderland Jr. — Storybook Theatre 2026 on 2026-06-27 at 19:30 — Grace Arts Live, 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  Upcoming event: Alice in Wonderland Jr. — Storybook Theatre 2026 on 2026-06-28 at 14:00 — Grace Arts Live, 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
```

---

## 3. Caveat (context quality, not “made up” names)

Program lines still include a generic **`schedule 09:00-10:00`** while **title, cost, note,** and **provider hours** carry the real offering. The model leaned on the right fields for this query. Tightening or clarifying **`schedule`** in the context builder would reduce grounding risk on other prompts.

---

## 4. Scope

- **No** additional real Anthropic API calls.
- **No** production `POST /api/chat` beyond prior verification; this document is DB + context builder only.
