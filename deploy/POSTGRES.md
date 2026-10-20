# PostgreSQL staging and migration

This is the development deployment for the durable-data branch. Production is
still on SQLite. Do not replace production until account migration, archive
batching, client receipts, restore tests and peak-load validation are complete.

Use `compose.postgres.yaml`. Every persistent mount is a host bind. PostgreSQL
17's data directory is explicitly mounted at `/var/lib/postgresql/data`; there
is no published database port and no Docker-managed volume. Review image updates
deliberately. The included limits are staging starting points, not measured
production capacity promises.

Create private host directories for `GABBAPROC_PG_DIR`, `GABBAPROC_SPOOL_DIR`
and `GABBAPROC_CONFIG_DIR`. The spool must be writable by UID/GID 18757 with mode
0700. Let the official database entrypoint establish ownership on a new empty
database directory; never mount over existing data. Validate mount labels on
SELinux hosts.

The private configuration directory contains:

- `postgres-password`: bootstrap/migration administrator password.
- `app-password`: separate restricted database login password.
- `admin-database-url`: connection URI for `gabbaproc_admin` at `postgres:5432/gabbaproc`.
- `app-database-url`: connection URI for `gabbaproc_app` at the same database.

Keep file access restricted while allowing the corresponding container UID to
read its individual mounted file. Percent-encode URI passwords. Never put these
files in Git or the domain docroot. The database initialization script runs only
for an empty data directory; password rotation on an existing database requires
an explicit role update and coordinated file replacement.

The migration container creates tables with an administrative role and grants
only data access to the application role. API and worker have automatic schema
creation disabled. Retain the old SQLite deployment template for rollback.

For migration, first pause writers and create a SQLite-consistent backup. Mount
that backup read-only in a one-off migration container and run
`python -m server.migrate --sqlite /backup/procs.sqlite3`. The destination must be
empty. Existing devices, token hashes, names, counters and available history are
copied in one destination transaction. The source is never modified. Independently
compare totals and ownership, then test uploads before switching the proxy.

The legacy `/api/imports` endpoint still responds only after processing. New
`POST /api/upload-jobs` returns 202 with a job ID; poll the authenticated
`GET /api/upload-jobs/{id}` until `processed`, `rejected`, `cancelled` or `failed`.
This initial queue transport accepts the existing bounded snapshot schema;
large-archive batching and out-of-order backfill are not implemented yet.

Worker imports and their receipts commit together. A transaction-scoped row lock
replaces leases for these bounded imports: a killed worker releases its lock and
the job remains queued. Retries use backoff; after ten failures the file remains
for operator inspection. Processed/cancelled/rejected files are cleaned up after
commit. Unregistered orphan files are removed after a day because no acceptance
receipt was issued; clients must retain unacknowledged uploads.

Do not back up the live PostgreSQL directory using an ordinary recursive copy.
Use PostgreSQL-aware backups and test restore of the database plus pending spool
files. The existing `backup.py` is SQLite-only and must not be used for PostgreSQL.
`backup-postgres.py` creates a private dump plus a spool archive while holding
the same filesystem lock as queue writers and cleanup. Workers can finish their
transaction, but payload files cannot disappear during the backup. Example:

```sh
python3 deploy/backup-postgres.py --container DATABASE_CONTAINER \
  --spool /srv/gabbaproc/spool --backups /var/backups/gabbaproc
```

Restore into an empty database with `pg_restore --exit-on-error`. Stop API and
worker before restoring the matching spool archive, preserve private ownership,
then reconcile job states before reopening uploads. Do not merge an older backup
into a live database. The script does not delete old backups; configure retention
and an external copy before production. A local database dump/restore has been
tested; production scheduling and full pending-job disaster recovery remain
cutover requirements.

Local integration tests require a dedicated database ending in `_test`:

```sh
GABBAPROC_TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:PORT/gabbaproc_test .venv/bin/pytest -q
```

This test option truncates test tables between cases. Do not point it at a live
database. Without it, legacy SQLite tests run and PostgreSQL queue tests skip.
