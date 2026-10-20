# Deployment

Production now uses PostgreSQL and a separate worker. See [production operations](PRODUCTION.md) and [PostgreSQL setup](POSTGRES.md).

## Previous SQLite deployment (rollback reference)

The previous production host configuration runs the Python 3.12 image defined here, with a dedicated UID, read-only root filesystem, bounded memory/PIDs and a private SQLite volume. Port 8757 is bound to loopback only. Set `FORWARDED_ALLOW_IPS` to the dedicated Docker network gateway used by the local proxy. Never use `*`.

Apache/Froxlor serves `web/` from the new domain docroot, proxies `/api/` to `http://127.0.0.1:8757/api/`, and manages Let's Encrypt. Disable PHP and directory listings for this domain. Set `LimitRequestBody 2097152`, `RequestReadTimeout header=10-20,MinRate=500 body=10,MinRate=500`, and the security headers from `server/app.py` for static pages too.

Generate a one-day single-use invite:

```sh
docker exec gabbaproc python -m server.admin invite
```

Keep the output private and deliver it to one participant. `list`, `approve COLLECTION_ID` and `revoke DEVICE_ID` are additional operator actions; check `python -m server.admin --help`.

For a deployment, build a new image from a tested revision, stop only the `gabbaproc` container, and recreate it with the same private data volume. Take a SQLite-consistent backup first (`sqlite3.Connection.backup`, not a live copy of only the main WAL database file). Do not deploy unrelated sites or regenerate Froxlor configuration by hand. Store and rotate backups outside the webroot. A prior image plus the compatible database backup provides rollback.

Production uses `gabbaproc-backup.timer` and the included `backup.py` for a daily integrity-checked SQLite backup with seven-day retention in `/var/backups/gabbaproc` (root-only). The service needs write access to the source directory for SQLite WAL shared-memory bookkeeping, while the database itself is opened with `mode=ro`.

`compose.yaml` is a neutral deployment template. Supply the required `GABBAPROC_*` environment variables locally; do not commit production paths or network details. Build with `docker compose -f deploy/compose.yaml build`, then `up -d`. Create the private data directory with owner `18757:18757` and mode `0700`. Sync only `web/` into your domain docroot, never the repository or private database.
