# Local companion archive test

This is an unreleased development build. No GitHub release workflow is needed.
Run `bash tools/build-local-appimage.sh` with local Podman. All build caches are
host directories below the ignored `desktop/target/local-build/` directory.
The container uses Ubuntu 22.04; cross-distribution runtime validation is still
required. This debug AppImage is approximately 134 MiB, not a release-size target.

The build has a separate application identifier and keyring entry. It does not
register/replace the normal desktop launcher. Update buttons are disabled so it
cannot replace itself with the production release. It defaults to the local API
`http://127.0.0.1:8771/api`. Debug builds alone may override this with
`GABBAPROC_TEST_API=http://127.0.0.1:PORT/api`; arbitrary remote hosts are rejected.
Release builds always use the production HTTPS endpoint.

Start an isolated PostgreSQL test API and worker using the development server
code before trying uploads. Use a test token and a copy of SavedVariables, not
production credentials. The live website does not yet run this queue protocol.

## Archive transport

Schema 2 packets repeat cumulative totals and contain at most 100 segments and
256 KiB of JSON. The server stores the latest cumulative totals once and can
backfill older history without rolling totals back. An incremental archive sum
index detects inconsistent totals across packets. Duplicate completed segments
are idempotent; changed completed segments are rejected.

The companion reads `archiveHistory` and `archivedExports` from the development
addon, falling back to legacy `history`. Only supported catalog effects enter
public uploads; custom effects are not yet supported by the server. Anonymous
packets contain no character names, realms, local paths or zone labels.

Before sending, packets are atomically written to a private per-token,
per-character local outbox. A 202 response is not an acknowledgement of import.
The cursor advances only for a matching `processed` receipt. Restart, missing
source files, network failures and rate limits leave the outbox intact. Retries
respect numeric Retry-After and use capped exponential backoff plus jitter.
Pending queues are checked separately from the configured new-export interval.
A manual upload continues polling and sending its existing selected queue even
when scheduled uploads are off. It stops after confirmation and does not collect
new exports automatically. Explicitly switching automatic uploads off pauses
background processing; closing the application also pauses it. After a restart,
click Upload again to resume a manual queue. Failed,
rejected or cancelled jobs remain visible and retained for operator resolution.

The optional bandwidth setting offers unlimited (default), 64, 128, 256, 512 or
1024 KiB/s and applies to manual and automatic packet bodies. Uploads are serial.
HTTP/TLS overhead is not part of this payload-byte limit. Changing the limit
while an upload is running requires waiting for that upload to finish.

SavedVariables input is bounded to 64 MiB and the local serialized queue to
128 MiB. Exceeding a limit reports an error without deleting the source archive.
These are safety limits, not automatic pruning or proof of unlimited retention.
WoW still writes SavedVariables only at reload/logout.

Validation performed locally: 25 PostgreSQL tests including a >8 MiB Lua file,
1,702 fights across two collections, 19 packets, replay and worker receipts;
13 Rust core tests; one native HTTP transport test for 429, persisted retry,
queued versus processed receipts and unavailable source files. Browser checks
cover the bandwidth choices, DE labels and development-build isolation.

Still required before a production release: native real-client WoW checks,
Windows/macOS filesystem and queue tests, production migration/backup recovery,
account login/device linking and representative concurrent large-archive load.

The prepared workstation test environment uses a separate
`gabbaproc_companion_test` database and local API port 8771. A private test token
is in `desktop/target/local-build/LOCAL-TEST-TOKEN.txt`; paste it into this test
app only. The API and worker run locally and need restarting after a reboot.
