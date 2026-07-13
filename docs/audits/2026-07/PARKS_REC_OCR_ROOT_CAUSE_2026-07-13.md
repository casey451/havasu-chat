# Parks & Rec data quality — root cause + fix plan (2026-07-13)

## Symptom
Live P&R events show wrong info: garbled titles (**"Kids & Clay Kids - Pickleball"**),
wrong times (**"Back to School - Kids Craft"** at 10:00 *and* 15:00 — WebTrac's real
program is "Kids Key Chain" at **17:15**), and scattered series (Line Dancing on
Sun 11:15 / Mon 10:00 / Sun 10:00).

## Root cause — two P&R feeds, one unreliable
| Source | Count (live, upcoming) | Reliability |
|---|---|---|
| **WebTrac** (`register.lhcaz.gov/webtrac`, real registration system) | 11 | **Correct** — verified 3 vs source, exact match (Sunrise Kayak 6am/Rotary Park, Kids Archery 9am, Dodgeball 5pm) |
| **Vision-OCR** of the monthly calendar image (`…/185/Parks-Recreation#cal|…`) | 38 | **Unreliable** — vision-LLM transcription of a PNG flyer (`ImageRepository/Document`, `image/png`), no per-event source to verify against |

Splitting the 38 OCR events:
- **~20 duplicate WebTrac programs** (Acrylic Painting, Clay, Watersports/Kayak,
  Pickleball, Mac & Cheese, …) — WebTrac has the correct version; the OCR copies
  are wrong duplicates.
- **~18 are free drop-in activities** (Line Dancing, E-Sports, Fishing Fridays,
  Glow Swim, Mexican Train Dominoes, Tiny Tots Open Gym, …) that WebTrac **does
  not carry** (confirmed: keyword search returns 0 real sections). The OCR
  calendar is their only source — and they are **real events**.

## Why the existing prevention missed it
- The ingest quality gate (#837) only holds **bare-address** venues; these carry a
  real-looking name ("Lake Havasu City Parks & Recreation").
- The nightly source-verify (#837) can't field-check OCR events — their "source"
  is a synthetic calendar anchor with **no per-event page** to compare against.
- The vision path sits outside both guards.

## Fix
**Immediate (this PR):** quarantine ALL 38 live OCR (`#cal`) events →
`pending_review` (reversible), so the wrong data leaves the public calendar now.
WebTrac events stay live. `scripts/parks_rec_ocr_quarantine_2026_07_13.py` +
`parks-rec-ocr-quarantine-apply.yml` (gated, undo snapshot).

**Durable (next, needs source confirmation):**
1. **WebTrac = authority** for every program it covers — make the WebTrac loader
   comprehensive and the single source for those ~20; never let OCR create a
   competing row (dedup/suppress).
2. **Free drop-in activities** (the ~18 WebTrac doesn't carry) are real and must
   work. The published source is a **PNG calendar image** (no text PDF found on
   the P&R page), so the reliable options are: a higher-fidelity extractor with
   **strict validation** (no garbled titles, sane times, known facilities) that
   **always lands pending for human review**, and/or a better upstream source if
   the city posts a text/PDF activity guide. **Open question for Casey:** where
   he's seen it as a PDF — that source would be far more reliable than OCR of the
   image.
