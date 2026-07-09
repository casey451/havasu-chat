# Nightly prod DB backup (`havasu-db-backup`)

A daily `pg_dump` of the prod Postgres to the VPS's local disk (164 GB free).
**Read-only against prod** — a logical dump takes a consistent snapshot and
writes nothing back. Output is a compressed, `pg_restore`-able custom-format dump;
dumps older than the retention window are pruned.

This is a defence-in-depth copy on infrastructure you control, independent of
Railway's own backups.

## Install (on the VPS, as root)

```bash
cd /opt/havasu-chat
sudo cp deploy/vps-backup/havasu-db-backup.service \
        deploy/vps-backup/havasu-db-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now havasu-db-backup.timer

# smoke test now (writes a real dump):
sudo systemctl start havasu-db-backup.service
journalctl -u havasu-db-backup.service -n 20 --no-pager
ls -lh /var/backups/havasu/
```

`DATABASE_URL` is read from `/etc/havasu/havasu-vision.env` (already on the box).
`pg_dump` is pinned to `/usr/bin/pg_dump` (must be ≥ the prod server major; Ubuntu
24.04 ships 18.x, prod is 18.x). Tune `BACKUP_DIR` / `RETENTION_DAYS` in the unit.

## Restore (when needed)

```bash
pg_restore --no-owner --no-privileges -d "<target-DATABASE_URL>" \
  /var/backups/havasu/havasu-<stamp>.dump
```
