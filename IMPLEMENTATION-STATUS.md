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

## Archive transport update — local development

Implemented since the initial checkpoint: version 2 bounded archive batches,
late history backfill, cross-batch cumulative consistency checks with an
incremental usage index, and a persistent companion outbox. The companion polls
server receipts and acknowledges only processed jobs. Network/rate-limit errors
retain data with persisted retry/backoff. Optional 64–1024 KiB/s bandwidth limits
apply to serial manual and automatic uploads; unlimited remains the default.

Validation: 25 PostgreSQL tests pass, including a >8 MiB Lua SavedVariables file
processed by the real Rust parser into 19 packets and 1,702 stored fights across
two collections. Thirteen core Rust tests and a native HTTP transport test pass.
The local AppImage uses an optimized build with the explicit `local-test` feature. See
[local companion test instructions](LOCAL-COMPANION-TEST.md). No release pipeline
was started for this work and the production deployment remains unchanged.

## Required before production cutover

1. Validate the new bounded archive batches and late backfill under representative
   concurrent load and interruptions. The published client still uses schema 1.
2. Validate the new companion outbox on Windows/macOS and in real WoW usage;
   define operator recovery for blocked jobs and long-running archive limits.
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
need further real-client validation. Zone export changes SavedVariables in memory; WoW writes the file
only on reload/logout. No new addon or companion release was published here.
