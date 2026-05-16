# Phase 5.4 — Health, Wellness & Care — Top-10 `crowd_notes` (staged)

> Mirrors `outputs/phase5_3_home_property_crowd_notes_top10_staged.md` shape.
> Closes Phase 5.4 acceptance gate item 4 ("Top-10 by reviews have long-form
> `crowd_notes`"). Notes use the locked Phase 5.1 JSON shape:
> `{"short": str, "long": str}`. Phase 6 consumes the absence-of-`long`
> signal (list-blurb vs profile-section).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.4 session
> (2026-05-16) post-`2858f8a` (mid-session checkpoint commit) + post-§5
> heat_exposure apply.

---

## §1 The Top 10 entries

| # | entity_id prefix | name | reviews | rating | type | verified |
|---|---|---|---|---|---|---|
| 1 | `7b3b9ad2` | Havasu Dental Center - Dr Ilan Shamos | 1610 | 4.9 | dentist | – |
| 2 | `2fb8ba0c` | NextCare Urgent Care, Lake Havasu City | 1589 | 4.6 | medical_clinic | – |
| 3 | `298b4e4f` | Skin and Cancer Institute - Lake Havasu | 1425 | 4.9 | doctor | – |
| 4 | `9901f739` | Thomas Dermatology | 1306 | 4.9 | skin_care_clinic | – |
| 5 | `c0c70cf4` | Lakeview Family Dental | 1098 | 4.8 | dentist | ✓ NPI 1952628984 |
| 6 | `0dc35bae` | Havasu Dentistry | 1071 | 4.9 | dentist | ✓ NPI 1396198263 |
| 7 | `c76c490b` | TrueCare Urgent Care | 903 | 4.8 | medical_clinic | ✓ NPI 1063051936 |
| 8 | `b30ec634` | Planet Fitness | 768 | 4.4 | gym | – |
| 9 | `17d02400` | Barnet Dulaney Perkins Eye Center | 761 | 4.7 | medical_clinic | ✓ NPI 1497727093 |
| 10 | `4f070a25` | Optima Medical - Central Lake Havasu City | 619 | 4.8 | medical_clinic | – |

> Drafted from `Provider.google_review_snippets` (own column, not inside
> `attributes` — corrected mid-session after the checkpoint §3 plan
> mis-routed to `attributes.google_review_snippets`; all 10 entries had
> n=5 real snippets cached during enrichment).

---

## §2 The drafts

### #1 — Havasu Dental Center - Dr Ilan Shamos (1610 reviews, 4.9★) — `7b3b9ad2`

```json
{
  "short": "Havasu's most-reviewed dentist — Dr. Shamos delivers same-day emergency care; reviewers note variable assistant interactions.",
  "long": "1,610 reviews at 4.9★ make this Havasu's highest-volume dental practice. Reviewers consistently single out Dr. Ilan Shamos for same-day appointments on broken crowns and tooth emergencies, painless crown work, and long-tenured patient relationships (multi-year, multi-decade). Front-desk staff get strong praise; assistant-level interactions are more variable, with a few pointed reviews about specific exchanges. Located on Jamaica Blvd S."
}
```

### #2 — NextCare Urgent Care, Lake Havasu City (1589 reviews, 4.6★) — `2fb8ba0c`

```json
{
  "short": "Urgent care with same-day appointments — PA Joie Tedder and PA Michelle get repeat callouts for thorough, patient-first visits.",
  "long": "1,589 reviews at 4.6★. The repeated-name pattern: PA Joie Tedder and PA Michelle are both singled out by multiple reviewers for spending real time on diagnosis, explaining preventative care, and listening rather than rushing. Same-day appointments for respiratory and acute issues are the typical use case; travelers and out-of-network patients give it strong marks. Wait times for booked appointments occasionally run long when the clinic is busy. Located on Mesquite Ave."
}
```

### #3 — Skin and Cancer Institute - Lake Havasu (1425 reviews, 4.9★) — `298b4e4f`

```json
{
  "short": "Dermatology that runs on time — Cassandra and Persephonie Tweeten get repeat callouts for thorough, unrushed exams.",
  "long": "1,425 reviews at 4.9★. Two providers dominate the reviews: Cassandra and PA Persephonie Tweeten — both repeatedly named for thorough mole and skin checks, on-time scheduling, and unrushed appointments. Short-notice availability and timely follow-up calls and messages are repeated themes. Located on Mesquite Ave in the medical corridor."
}
```

### #4 — Thomas Dermatology (1306 reviews, 4.9★) — `9901f739`

```json
{
  "short": "Medical + cosmetic dermatology — PAs Alice D. and Nikki Guzzo take the time for complex cases.",
  "long": "1,306 reviews at 4.9★. Reviewers consistently name PAs Alice D. and Nikki Guzzo as the standout providers — Alice for complex long-term skin conditions where she lays out treatment options patiently, Nikki for thorough exams with strong patient education. MAs Mindy, Amy, and Taylor get repeat callouts for warm front-of-house. Both medical and cosmetic dermatology services. Located on Mesquite Ave."
}
```

### #5 — Lakeview Family Dental (1098 reviews, 4.8★) — `c0c70cf4`

```json
{
  "short": "Family dentistry with a strong hygienist team — Jessica and Rachel get repeat callouts for thorough, anxiety-friendly cleanings.",
  "long": "1,098 reviews at 4.8★. Drs. Lynn and Osbon lead the practice; hygienists Jessica and Rachel are named most often in reviews, specifically for thorough cleanings and an upbeat, anxiety-friendly approach. A repeated reviewer pattern: California transplants finding a new dentist they trust after long-term out-of-state relationships. NPI-verified. Located on Lake Havasu Ave."
}
```

### #6 — Havasu Dentistry (1071 reviews, 4.9★) — `0dc35bae`

```json
{
  "short": "Dentistry with same-day emergency crown work — Dr. Kurtz and team get strong reviewer praise; front-office interactions occasionally noted as cooler.",
  "long": "1,071 reviews at 4.9★. Reviewers single out Dr. Kurtz and hygienist Liz for a warm, informative chair-side approach, plus same-day emergency work — a notable thread is travelers (boondockers, Quartzsite RVers) getting fit in for emergency crown replacements. Assistants Amber, Wendy, and Jade get repeated positive callouts. A small number of reviews flag front-office and finance interactions as less warm. NPI-verified. Located on McCulloch Blvd N."
}
```

### #7 — TrueCare Urgent Care (903 reviews, 4.8★) — `c76c490b`

```json
{
  "short": "Modern urgent care with online appointments and a spotless facility — most visits are quick, with electronic results delivery.",
  "long": "903 reviews at 4.8★. Reviewers consistently call out the facility itself (spotless, modern) and the workflow (online appointments, fast electronic results) as differentiators vs. peer urgent-care clinics. Most visits described as quick start-to-finish; the negative outliers involve longer waits and front-desk friction on more complex visits. NPI-verified. Located on Mesquite Ave."
}
```

### #8 — Planet Fitness (768 reviews, 4.4★) — `b30ec634`

```json
{
  "short": "Busy budget gym — Saylor and Tyler get repeat callouts for upbeat service and clean equipment; Black Card popular with RVers passing through.",
  "long": "768 reviews at 4.4★. Staff named in reviews — Saylor and Tyler for the floor, Raven for signups — consistently get warm praise for upbeat service and well-maintained equipment. Notable secondary use case: RV travelers and road-trippers using the Black Card for showers and hydromassage as they pass through Havasu. Peak hours run crowded; one full-time trainer covers a large member base. Located on McCulloch Blvd N."
}
```

### #9 — Barnet Dulaney Perkins Eye Center (761 reviews, 4.7★) — `17d02400`

```json
{
  "short": "Eye care with Dr. Senica strongly preferred — reviewers consistently flag overbooking on busy days.",
  "long": "761 reviews at 4.7★. Dr. Senica (sometimes spelled Seneca in reviews) is the standout — repeatedly named for unrushed exams and genuine patient relationships; Dr. Sipperly also gets positive mentions. Reviewers' repeated criticism is overbooking on peak days, with multi-hour waits noted; regulars suggest booking early-morning or late-afternoon slots. NPI-verified. Located on Capri Blvd."
}
```

### #10 — Optima Medical - Central Lake Havasu City (619 reviews, 4.8★) — `4f070a25`

```json
{
  "short": "Multi-provider primary care — FNP April, Dr. Ashley Mulder, Cynthia Harper, and Christian Grandell each have their own named-by-name fan base.",
  "long": "619 reviews at 4.8★. The reviewer pattern: this is a multi-provider primary-care office where FNP April, Dr. Ashley Mulder, FNP Christian Grandell, Cynthia Harper, and Dr. Rozelle each have their own named-by-name following. A recent practice merger/buyout brought transfer patients in; reviewers note Megan at check-in for going out of her way on pricing and scheduling. Located on Mesquite Ave."
}
```

---

## §3 Notes on drafting choices

- **Names spelled as in the snippets** — including the Senica/Seneca variant for #9 (reviewers themselves spell it both ways), Dr. Allen/Alan for #6, and the various PA spellings. Reflecting reviewer language, not correcting it.
- **Mixed-experience entries (#1, #6, #7, #9)** include a one-line acknowledgement of the negative pattern. This matches the 5.3 Sears Appliance Repair entry's "mixed tech quality" treatment — honest > glowing.
- **No fabricated specifics.** Every named person, location, and service detail is grounded in the n=5 snippets I read for that entry. Where snippets disagree on spelling, I noted it explicitly (e.g., Senica/Seneca).
- **NPI-verified flag** mentioned for entries 5/6/7/9 — small operator-discoverability nudge.
- **No address claims beyond what the `providers.address` column already stores** — only neighborhood-level mention (street name).

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.4 session (2026-05-16).
Source: `Provider.google_review_snippets` column, top-10 by
`google_review_count` in `health-wellness-care`. Apply via
`outputs/apply_phase5_4_health_wellness_crowd_notes.py`.*
