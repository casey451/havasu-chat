# Self-hosted vision model for the image scrapers (no token spend)

The vision scrapers (`app/contrib/vision_calendar.py` → Parks & Rec calendar /
flyers, Senior Center flyers) call an **OpenAI-compatible** chat-completions
endpoint. By default that's OpenAI (`OPENAI_API_KEY`). Point it at a model you run
yourself — e.g. **Ollama on your Hostinger VPS** — and you pay nothing per call.

This mirrors how `app/core/embeddings.py` already supports a local embeddings
server, so the pattern is consistent across the codebase.

## The switch (env vars)

| Env var | Effect |
|---|---|
| `VISION_BASE_URL` | Set it → use a self-hosted OpenAI-compatible endpoint instead of OpenAI. e.g. `http://127.0.0.1:11434/v1` (Ollama on the same host). **Unset → OpenAI.** |
| `VISION_API_KEY` | Optional. Local servers ignore it; defaults to `"local"`. Set it to the bearer token if you put the endpoint behind an auth proxy. |
| `VISION_MODEL` | The served model name, e.g. `qwen2.5vl:3b`, `minicpm-v`, `llama3.2-vision`. (Falls back to the legacy `PARKS_REC_VISION_MODEL`, then `gpt-4o`.) |
| `VISION_CALENDAR_TILES` | Split each calendar image into N overlapping bands before reading (default `1` = off). **Set `2` on a CPU box** — the robust fix for dense grids (below). |
| `VISION_MAX_TOKENS` | Max reply tokens (default `4096`, both backends; Ollama maps it to `num_predict`). |
| `VISION_NUM_CTX` | Requested context window (default `8192`). **Ignored by Ollama's `/v1` endpoint** (see below); kept for OpenAI-compatible servers that honor it (vLLM). |

No code change is needed to switch — set the vars where the scraper runs.

### If the calendar returns 0 events (truncation)

A dense, recurring-heavy grid (~30 events) is too much for a small CPU model to
emit in one reply — the JSON gets cut off and is unparseable. You'll now see a
`WARNING` like `N chars of model output failed to parse (likely truncated ...)` in
the logs (previously this silently looked like "fetched 0 / read nothing").

**Two distinct limits cause this, both confirmed on the VPS:**
- *Context* — the image fills the window. **Ollama's `/v1` endpoint ignores a
  per-request `num_ctx`**, so raising `VISION_NUM_CTX` does nothing there; the
  model stays at its built-in 4096.
- *Output* — the event list is simply long. Bounded by `VISION_MAX_TOKENS` /
  Ollama's `num_predict`.

**Fix, in order of preference:**
1. **Tile it: `VISION_CALENDAR_TILES=2`** (recommended). Each band is a smaller
   image with a shorter list, satisfying *both* limits at the default window — and
   it's *faster* per call. Rows are merged + deduped across the overlap. Bump to
   `3` if a single tile still truncates.
2. **Or bake a bigger window** into a model variant (no tiling): build
   `deploy/vps-vision/havasu-qwen-cal.Modelfile`
   (`ollama create qwen2.5vl-cal -f ...`), then set `VISION_MODEL=qwen2.5vl-cal`
   and `VISION_MAX_TOKENS=8192`. Slower (~15–25 min/run) — raise `TimeoutStartSec`.

Flyers emit one short event and never hit this, so they work at any setting.

## Recommended setup: Ollama on the VPS

```bash
# on the Hostinger VPS
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5vl:3b      # good document/OCR model, light enough for CPU
ollama serve                  # serves OpenAI-compat at http://127.0.0.1:11434/v1
```

### Which model (Hostinger VPS is CPU-only — no GPU)

Pick by RAM; bigger = more accurate but slower on CPU. For a low-volume scraper
(a couple of images every other day) even slow CPU inference is fine.

| RAM | Model | Notes |
|---|---|---|
| 4–8 GB | `qwen2.5vl:3b` or `granite3.2-vision:2b` | Document/table/OCR focused; the practical floor for reading a calendar grid |
| 8–16 GB | `minicpm-v` (8B) | Strong OCR; the sweet spot if you have the RAM |
| 16 GB+ | `llama3.2-vision:11b` | Best quality of the CPU-feasible options; slowest |

**Honest caveat:** a packed **monthly calendar grid** (tiny dense text) is the
hard case for small local models — expect lower recall than `gpt-4o`. Individual
**flyers** (sparse text) are much easier and work well even on small models. The
engine's guards (provenance / month-bounding / confidence-held-hidden) drop bad
rows, and everything lands **pending for `/admin` review**, so a weaker model
fails safe (less data, not wrong live data). Test on a real July calendar image
and compare before trusting it.

## Where the scraper runs (networking)

The cron currently runs in **GitHub Actions**, which can't reach a private VPS.
Two options:

1. **Run the scrape on the VPS itself (recommended for local models).** Move the
   three `--apply` commands from `.github/workflows/parks-rec-scrapes.yml` into a
   VPS `cron`/systemd timer. The scraper then talks to Ollama over `localhost`
   (`VISION_BASE_URL=http://127.0.0.1:11434/v1`) — nothing is exposed, and it
   needs `DATABASE_URL` (prod Postgres) on the VPS. Drop the vision step from the
   GitHub workflow so it doesn't double-run.
2. **Keep the cron in Actions, expose the VPS endpoint.** Ollama has **no
   built-in auth**, so never expose `:11434` directly. Put a reverse proxy
   (Caddy/nginx) or a Cloudflare Tunnel in front with a bearer token, set
   `VISION_BASE_URL` to the public HTTPS URL and `VISION_API_KEY` to the token
   (GitHub Actions secret). Firewall the raw port.

Option 1 is simpler and safer for a self-hosted model.

## Cost reality check

The current OpenAI usage here is small — roughly a few cents per run, on the order
of **$2–5/month** at the present cadence. Self-hosting saves little *today*; it
pays off if you add many more image scrapers, want to avoid per-call billing on
principle, or need the data to stay on your own box. If volume stays low, the
managed API may simply be cheaper than the VPS RAM/maintenance.

## Alternative: OCR instead of a vision LLM

For pure text extraction, a CPU OCR engine (PaddleOCR, Tesseract) is free and
light, but it returns raw text without the structured event reasoning the vision
prompt does. A hybrid (OCR → a small local text LLM to structure) is possible but
more moving parts than pointing `VISION_BASE_URL` at one multimodal model.
