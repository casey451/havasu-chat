# Cowork review runbook — Facebook screenshot captures

Run this in a Cowork session ("run the capture review runbook in docs/scraper/").
It is the "brain" half of the scraper: OpenClaw uploads dumb screenshots; this
pass vision-reads them, categorizes findings per the data contract, and compiles
a report for Casey. NOTHING auto-publishes — output is a report + status flips.

## Auth
The API token is `INGEST_API_TOKEN` in the repo-root `.env` (gitignored).
Read it from there: `grep ^INGEST_API_TOKEN .env`. If absent, ask Casey to add it
— never paste the token value into chat, reports, or committed files.

Base URL: `https://havasu-chat-production.up.railway.app`

## Steps

1. **Fetch the queue**
   `GET /api/ingest/captures?status=new&limit=50` with `Authorization: Bearer <token>`.
   Also fetch `status=flagged` rows — these are OpenClaw problem reports (no image);
   list them in the report under "Problems for Cowork/Casey" with their notes.

2. **Vision-read each capture**
   Download each image (R2 URL in the capture row) to the local outputs folder and
   Read it (Claude vision). Extract only what is actually legible — do not infer.

3. **Categorize per `havasu_scraper_data_contract.md`** (same folder):
   - Ongoing deal (happy hour, taco Tuesday…) → proposed `Offering` + `Schedule`
     (name, description, price_text, days_of_week, start/end time).
   - Dated happening (concert, one-off event) → proposed `Event`
     (title, date, start_time, location_name, description, source_url).
   - Recurring happening (weekly trivia/live music) → recurring `Event` + rrule.
   - Not useful (memes, generic photos, ads with no offer/date) → mark "skip".
   - Unreadable/ambiguous → mark "needs Casey".

4. **Compile the review report** → `docs/scraper/reports/capture_review_<YYYY-MM-DD>.md`:
   per venue: capture id, screenshot thumbnail link (source R2 URL), what was read,
   proposed record (type + fields), confidence, recommendation
   (ingest / skip / needs Casey). End with the flagged-row problem list and
   a quality tally (legible %, useful %).

5. **Flip statuses**: for every capture processed,
   `PATCH /api/ingest/captures/{id}` body `{"status": "reviewed"}`
   (use `discarded` only for exact-duplicate images). Leave anything marked
   "needs Casey" as `new` so it stays in the queue, and say so in the report.

6. **Stop.** Present the report to Casey. Do NOT create Offerings/Events/
   Contributions from the findings — publish path comes only after Casey's
   sign-off on report quality (and the publish auth path isn't built yet).

## Watch-outs
- FB CDN URLs in screenshots may show stale dates — trust the post date visible
  in the image, else `captured_at`.
- DeepSeek never extracted anything; everything in the image is unvalidated raw.
- Duplicate venues: Turtle Beach Bar and The Turtle Grille share one FB page.
- First batch venues: Barley Brothers, College Street Brewhouse, The Office
  Cocktail Lounge, Flying X Saloon, Javelina Cantina.

## Scheduling (later)
After Casey approves the first report, schedule this to run daily (Cowork
scheduled task: "run docs/scraper/COWORK_REVIEW_RUNBOOK.md"). Not before.
