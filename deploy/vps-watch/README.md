# VPS watchdog (`havasu-watch`)

A 5-minute systemd timer that checks prod `/health`, the vision-scrape unit's
last-run freshness/exit status, and disk usage, and **emails only on a state
change** (fail or recovery) via the app's existing Resend sender. Steady-state
green is silent.

## Install (on the VPS, as root)

```bash
cd /opt/havasu-chat
# 1) env (holds the Resend key -> 0600)
sudo install -m 600 -o root -g root \
  deploy/vps-watch/havasu-watch.env.example /etc/havasu/havasu-watch.env
sudo nano /etc/havasu/havasu-watch.env   # set WATCH_ALERT_EMAIL, RESEND_API_KEY, RESEND_FROM_ADDRESS

# 2) units
sudo cp deploy/vps-watch/havasu-watch.service deploy/vps-watch/havasu-watch.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now havasu-watch.timer

# 3) verify
sudo systemctl start havasu-watch.service   # one-shot run now
journalctl -u havasu-watch.service -n 20 --no-pager
```

Runs **log-only** until `WATCH_ALERT_EMAIL` + Resend vars are set — safe to
install first. `python scripts/vps_watch.py --status` prints current state and
never alerts.
