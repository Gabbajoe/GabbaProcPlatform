# Production cutover — 2026-10-20

The public portal, PostgreSQL API and bounded single worker are live. The
CurseForge addon installation link is next to the companion download. These are
separate tools: the addon collects measurements, the companion uploads exports.

The deployment uses the compose definition with private host configuration and
an image override for `gabbaproc:0.1.2`. PostgreSQL has no public port. Only the
API is published on loopback port 8757 for the existing Froxlor Apache proxy.
Every persistent mount is a host bind; no Docker-managed data volumes are used.
Credentials remain in private files on the host, never in this repository.

Migration preserved the existing device/token hashes and invitations. Before
cutover there were no production owners, collections, totals or segments. A
consistent SQLite backup and the old webroot were retained. The previous
container is stopped, not removed. Do not simply restart it after PostgreSQL has
accepted new data: a rollback then requires reconciling those new writes.

Checks completed:

- SQLite integrity and imported row counts.
- Real queued uploads, processed receipts, duplicate replay and retained history.
- Old synchronous upload endpoint and quarantine handling.
- The same enrollment/upload/processing tests through public HTTPS.
- All five pages, both languages, CurseForge link and mobile layout.
- PostgreSQL dump restored into a separate temporary database successfully.
- Daily database-plus-spool backup timer active; the old SQLite job was replaced.

Backup retention and external backup replication still need operational setup;
current PostgreSQL backups are retained without automatic deletion. Large
backlogs, pending-job disaster recovery and production proxy load beyond the
local 200-client exercise still need validation. No claim of unlimited capacity
or full disaster-recovery readiness is made.

Account/OAuth/email login remains unavailable. Operators can create one-use,
24-hour invitations inside the API container without requesting schema changes:

```sh
docker exec gabbaproc-v2-api-1 python -c 'from server.storage import invite; print(invite())'
```

Treat that output as a secret. Five requested invitations were delivered only in
a private local file; none are included here. Those five invitations were explicitly
extended through 2026-10-31 23:59:59 Europe/Berlin and remain single-use.
Activation is on `/account.html`.
The operator CLI's initialization step should run only with migration credentials.

Desktop 0.1.2 must be published only after all platform artifacts and updater
signatures have been verified. Local `local-test` builds continue using their
separate localhost API and do not turn into production clients automatically.
