# Initial pilot validation — 2026-10-20

Companion source: `cb7b344b358441519779fc90e635baf3b60a95f8` (0.1.0). Later documentation/deployment-tool changes do not change the compiled app.

- 15 API tests: strict payload rejection, ownership, invites, monotonic counters, duplicate imports, visibility changes, deletion, quarantine and size limits.
- 5 Rust core tests: data-only Lua parsing, execution rejection, duplicate/depth/string limits, Unicode and anonymous allowlisting.
- End-to-end fixture produced by the real addon export code, serialized as Lua, parsed by the Rust reader and accepted by the strict Python server schema. Private labels were absent from the resulting JSON.
- Live HTTPS smoke test: invite enrollment, quarantined synthetic upload, duplicate handling and deletion/revocation. Test measurements were deleted; no synthetic records were added to public statistics.
- Browser checks: English/German, 390px mobile layout, table rendering, CSV download and inert rendering of injected name markup. No JavaScript or CSP errors observed. App UI controls tested using a simulated Tauri bridge.
- Linux AppImage launched locally for 15 seconds without reported startup errors. This is a smoke test, not a complete gameplay or keyring integration test.
- Windows x64, Linux x64, macOS ARM64 and macOS Intel packages built in [the release workflow](https://github.com/Gabbajoe/GabbaProcPlatform/actions/runs/39335977467).
- All five update artifacts independently verified with minisign against the public key compiled into the app. An altered Windows artifact was rejected. `latest.json` includes all four OS/architecture targets and installer-specific entries.
- Private daily SQLite backup completed with an integrity check; retention is seven days.
- Addon 0.1.1 logout/reload export regression tests pass in both locales. GitHub release and CurseForge upload succeeded.

Still requiring real-device acceptance: Windows/macOS first launch, OS-specific keyring/autostart behavior, a complete upgrade from 0.1.0 to a later version, and prolonged real WoW collection. Initial installers do not have Microsoft Authenticode or Apple notarization identities; mandatory updater signatures are a separate mechanism. This release is an invitation-based community-data pilot, not an audited anti-cheat system.

## Fedora RPM addition (2026-10-20)

- GitHub Actions run 39367988544 built the additional 0.1.0 x86_64 RPM successfully; API/core validation and repository CI passed.
- RPM metadata and file list inspected; MIT license, version 0.1.0-1, desktop entry and icons present. Download size: 3,941,383 bytes.
- Fedora 44 `dnf --assumeno install` resolved the package plus WebKitGTK/JavaScriptCore dependencies. No system packages were installed. Native RPM GUI launch and a future RPM-to-RPM updater installation remain untested.
- All six updater payloads independently verified against the compiled minisign public key. Added `linux-x86_64-rpm` while retaining the AppImage default and other format targets. Refreshed checksums.
- Corrected an existing Windows manifest signature left stale by run 39338059130 failing during a concurrent manifest replacement. Release matrix uploads now run serially to prevent this race.
