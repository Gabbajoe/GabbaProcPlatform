# Development checkpoint — 2026-10-20

Branch: `feature/durable-data-platform`. This is unfinished development, not a
production release. The live platform still uses the existing SQLite deployment.

## Implemented and locally checked

- PostgreSQL adapter, bounded connection pool, migration from a SQLite backup,
  and separate database roles. Deployment uses host bind mounts only.
- Durable file queue with quotas, authenticated receipts, retry backoff, worker
  resource limits, checksum validation, and transactional import/receipt updates.
- Server imports retain previously received segments; completed segments cannot
  be rewritten. Legacy synchronous clients retain their existing API semantics.
- Database and spool backup helper; a local database dump/restore was checked.
- Blue, bilingual data portal with separate measurement, comparison, quality,
  download and account pages. Account login is explicitly marked unavailable.
- Froxlor forwarding `gabbaproc@kellerkind.info` → `mail@nilskeller.de` is live;
  the Postfix lookup was verified. This does not configure outgoing login mail.

Validation: PostgreSQL integration suite 20 passed; SQLite compatibility suite
17 passed, 3 PostgreSQL-only tests skipped. Addon Lua tests pass in its separate
`feature/durable-exports` branch. Portal browser checks covered routes, language,
filters, inert markup in dataset labels, and a 390px viewport.

A local 200-client ASGI test imported 200 unique small fixtures, then replayed
them without duplicate counts. It made 453 requests including 53 retryable
overload responses. HTTP p95 was 2.617 seconds; unpaced worker processing took
0.237 seconds. This is not a production HTTP/proxy or large-backlog benchmark.

## Required before production cutover

1. Define and implement bounded archive batches and out-of-order history backfill.
   The current queue accepts legacy schema 1 with at most 301 segments per upload.
2. Extend the companion to read the addon's full archive and reset collections,
   persist pending batches locally, poll receipts, and retry safely. The current
   companion still uses the legacy synchronous endpoint.
3. Complete account, identity, session, device-pairing and email-login code.
   Register OAuth applications and configure outgoing mail; none are active yet.
4. Test worker interruption, pending-job disaster recovery, large archives,
   disk-full behavior and representative 200-user traffic through HTTP/proxy.
   Add operator retry/monitoring and scheduled backup retention/offsite copies.
5. Review the actual host resources, render/test the deployment configuration,
   test migration/rollback, then schedule the production cutover.

The addon branch adds opt-in zone snapshots and a full local combat archive,
including collections retained through reset. The UI and legacy export retain
their 300-entry view. Archive memory/file growth and companion support still
need work. Zone export changes SavedVariables in memory; WoW writes the file
only on reload/logout. No new addon or companion release was published here.
