# Self-hosting

The production host runs the Python 3.12 image defined here, with a dedicated UID, read-only root filesystem, bounded memory/PIDs and a private SQLite volume. Port 8757 is bound to loopback only. The Docker network gateway 172.30.87.1 is the only trusted forwarded-header source. Adapt it if changing the network.

Apache/Froxlor serves `web/` from the new domain docroot, proxies `/api/` to `http://127.0.0.1:8757/api/`, and manages Let's Encrypt. Disable PHP and directory listings for this domain. Set `LimitRequestBody 2097152`, `RequestReadTimeout header=10-20,MinRate=500 body=10,MinRate=500`, and the security headers from `server/app.py` for static pages too.

Generate a one-day single-use invite:

```sh
docker exec gabbaproc python -m server.admin invite
```

Keep the output private and deliver it to one participant. `list`, `approve COLLECTION_ID` and `revoke DEVICE_ID` are additional operator actions; check `python -m server.admin --help`.

For a deployment, build a new image from a tested revision, stop only the `gabbaproc` container, and recreate it with the same private data volume. Take a SQLite-consistent backup first (`sqlite3.Connection.backup`, not a live copy of only the main WAL database file). Do not deploy unrelated sites or regenerate Froxlor configuration by hand. Store and rotate backups outside the webroot. A prior image plus the compatible database backup provides rollback.
