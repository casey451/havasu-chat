# Run the vision image scrapers on your VPS (no token spend)

This kit runs the Ask Hava vision scrapers (Parks & Rec calendar + flyers, Senior
Center flyers) on your own VPS against a **local** vision model (Ollama), so there
is no OpenAI per-call cost and the model endpoint never leaves localhost.

It depends on the `VISION_BASE_URL` hook (PR #509) and the scrapers from #507/#508.
Background + model/networking/cost trade-offs: `docs/scraper/LOCAL_VISION_VPS.md`.

**Safety recap:** these three sources are NOT auto-approve, so every ingested row
lands **PENDING for `/admin` review** — nothing reaches users unreviewed. The
senior step does not touch the live senior loader. Each source runs independently
and failures are non-fatal.

---

## 1. Install the model server

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5vl:3b      # pick per RAM — see LOCAL_VISION_VPS.md
systemctl enable --now ollama # serves OpenAI-compat at http://127.0.0.1:11434/v1
```

## 2. Put the repo + venv on the VPS

```bash
sudo useradd --system --create-home --home-dir /opt/havasu-chat havasu || true
sudo -u havasu git clone https://github.com/casey451/havasu-chat /opt/havasu-chat
cd /opt/havasu-chat
sudo -u havasu python3 -m venv .venv
sudo -u havasu .venv/bin/pip install -r requirements.txt
```

**Self-update (built in).** `run_vision_scrapes.sh` does a non-fatal
`git -C "$HAVASU_REPO_DIR" pull --ff-only` as its first step, so every timer run
picks up the latest CI-gated `main` before scraping — a shipped fix reaches the
live scraper on its own, no manual pull. It runs as the repo-owning `havasu` user
(no git "dubious ownership"), is fast-forward-only (never force-moves a
dirty/diverged checkout), and logs the resulting short SHA. A failed/blocked pull
just runs the existing checkout. Set `HAVASU_GIT_PULL=0` to pin a checkout and
skip the pull. **Bootstrap:** after first installing (or after the PR that added
this) the box needs ONE manual `git pull` to pick up the self-updating script;
from then on it updates itself.

## 3. Configure the environment

```bash
sudo mkdir -p /etc/havasu
sudo install -m 600 deploy/vps-vision/havasu-vision.env.example /etc/havasu/havasu-vision.env
sudo nano /etc/havasu/havasu-vision.env     # set DATABASE_URL + VISION_MODEL
```

`DATABASE_URL` is the same prod Postgres string the Railway app uses. The file is
`chmod 600` because it holds DB credentials.

## 4. Smoke-test BEFORE enabling the timer

```bash
# Dry-run first (writes nothing) — confirm the local model actually reads the image:
sudo -u havasu env $(grep -v '^#' /etc/havasu/havasu-vision.env | xargs) \
  /opt/havasu-chat/.venv/bin/python /opt/havasu-chat/scripts/parks_rec_calendar_pull.py
```

You want a non-zero `fetched` count and sane sample rows. Calendar grids are the
hard case for small models — if recall is poor, try a bigger `VISION_MODEL`
(`minicpm-v`, `llama3.2-vision`) or rely on the flyers, which read reliably.

The env template sets **`VISION_CALENDAR_TILES=2`** — it splits each calendar into
two overlapping bands so the dense grid doesn't overflow a small CPU model's
context/output (which otherwise truncates → `fetched: 0`). If a tile still
truncates, raise it to `3`; see `docs/scraper/LOCAL_VISION_VPS.md` for the why
(including the Ollama `num_ctx` caveat) and the no-tiling Modelfile alternative.

Then a real run (lands pending):

```bash
sudo -u havasu /opt/havasu-chat/deploy/vps-vision/run_vision_scrapes.sh
```

Review the new pending rows in `/admin` before trusting the feed.

## 5. Enable the timer

```bash
sudo cp deploy/vps-vision/havasu-vision-scrape.service /etc/systemd/system/
sudo cp deploy/vps-vision/havasu-vision-scrape.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now havasu-vision-scrape.timer
systemctl list-timers havasu-vision-scrape.timer        # confirm next run
journalctl -u havasu-vision-scrape.service -n 50         # logs after a run
```

## 6. Turn OFF the GitHub Actions copy

Once the VPS timer runs cleanly, remove the **"Vision calendar/flyer ingest"**
step from `.github/workflows/parks-rec-scrapes.yml` so the scrapers don't run in
two places. (It is currently a no-op there — no `OPENAI_API_KEY` Actions secret —
so there is no rush, and no gap if you do this after step 5.)

---

## Security notes

- **Never expose Ollama's `:11434` to the internet** — it has no auth. Keeping the
  scraper on the same VPS means `VISION_BASE_URL=http://127.0.0.1:11434/v1` and
  nothing is published. If you must call it remotely, front it with a reverse
  proxy + bearer token and set `VISION_API_KEY`.
- `/etc/havasu/havasu-vision.env` is `chmod 600` (DB creds). The systemd unit runs
  as the unprivileged `havasu` user with `NoNewPrivileges` + `ProtectSystem`.
