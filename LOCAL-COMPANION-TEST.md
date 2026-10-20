# Local companion archive test

This is an unreleased development build. No GitHub release workflow is needed.
Run `bash tools/build-local-appimage.sh` with local Podman. All build caches are
host directories below the ignored `desktop/target/local-build/` directory.
The container uses Ubuntu 22.04; cross-distribution runtime validation is still
required. The optimized dev.4 AppImage is approximately 79 MiB (the previous
debug build was approximately 134 MiB).

The build has a separate application identifier and keyring entry. It does not
register/replace the normal desktop launcher. Update buttons are disabled so it
cannot replace itself with the production release. It defaults to the local API
`http://127.0.0.1:8771/api`. Debug builds and builds with the explicit `local-test`
feature may override this with
`GABBAPROC_TEST_API=http://127.0.0.1:PORT/api`; arbitrary remote hosts are rejected.
Release builds without `local-test` use the production HTTPS endpoint.

Development build dev.4 loads saved credentials in the background and searches
for characters outside the UI thread. Loading feedback remains visible while
these operations run. Existing development preferences and queued uploads are
preserved. For timing diagnostics, set `GABBAPROC_STARTUP_TRACE=1`; stderr then
contains elapsed milliseconds for startup phases, without tokens or file paths.
On the development workstation, one warm launch with
`APPIMAGE_EXTRACT_AND_RUN=1` reached the page-loaded event in 524 ms from launcher
invocation (175 ms inside the application). This is a local measurement, not a
cold-start or cross-platform guarantee. Browser checks also cover a deliberately
delayed scan and credential load while other controls remain usable.

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

Development build dev.3 adds per-character upload progress. Percentages count
server-confirmed packets, not bytes sent. Preparing, sending, checking, waiting,
retry, pause, error and completed states are localized. A local one-second UI
refresh drives the countdown without increasing server polling. Native tests
assert that a queued receipt remains at zero confirmed and only a processed
receipt reaches completion; browser tests cover the visible state transitions.

Development build dev.5 separates uploaded packets (blue) from processed packets
(turquoise). Upload progress advances when the server returns a receipt, not when
bytes merely leave the client. Processing advances only on processed receipts.
Both percentages count packets, not bytes. The progress heading uses the locally
discovered character name and realm; these labels do not change upload privacy.
A badge shows whether the queued payload is anonymous or includes name and realm.
The existing sequential transport and confirmation polling interval are unchanged.

The companion uses Characters, Sync, Account and Settings tabs with keyboard
navigation. Only the active panel scrolls; navigation stays visible. The header
reports whether upload credentials are loaded, not whether the server is online.
On first launch the UI follows the system language (German, otherwise English).
An explicit language selection is retained across restarts.
