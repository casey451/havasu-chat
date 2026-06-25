# Link-health sweep (`havasu-linkcheck`)

A periodic sweep that checks every stored outbound URL (provider websites +
Facebook, live event URLs), records each into the `link_health` table, and
**emails a summary of newly-confirmed-broken links** (a link must fail multiple
consecutive sweeps before it's flagged, so transient blips and big-site
rate-limits don't page). Read-only against the source data — it *flags* dead
links, never edits provider/event rows.

Runs at low priority and **pauses while the vision scrape or nightly backup are
running**, so it only fills the box's idle time.

## Install (on the VPS, as root)

```bash
cd /opt/havasu-chat
sudo cp deploy/vps-crawler/havasu-linkcheck.service \
        deploy/vps-crawler/havasu-linkcheck.timer /etc/systemd/system/
sudo systemctl daemon-reload

# Dry-run first (no writes) to eyeball the report:
sudo -u havasu bash -c 'set -a; . /etc/havasu/havasu-vision.env; set +a; \
  .venv/bin/python scripts/link_health_scan.py --workers 8'

# Then enable the scheduled sweep (writes link_health + emails on new breakage):
sudo systemctl enable --now havasu-linkcheck.timer
sudo systemctl start havasu-linkcheck.service   # run one sweep now
journalctl -u havasu-linkcheck.service -n 30 --no-pager
```

Reads `DATABASE_URL` from `/etc/havasu/havasu-vision.env` and the email settings
(`WATCH_ALERT_EMAIL`, `RESEND_*`) from `/etc/havasu/havasu-watch.env`. The CLI is
dry-run by default; `--apply` persists, `--email-summary` emails new breakage.
