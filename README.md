# ⚡ GabbaProc Platform

![Checks](https://github.com/Gabbajoe/GabbaProcPlatform/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-gold)
![Languages](https://img.shields.io/badge/languages-English%20%2F%20Deutsch-teal)

Community proc research for WoW Classic Era / Hardcore. Website, API and lightweight Tauri companion, openly maintained in one repository.

**[Website](https://gabbaproc.kellerkind.info) · [Companion releases](https://github.com/Gabbajoe/GabbaProcPlatform/releases) · [Addon on CurseForge](https://www.curseforge.com/wow/addons/gabbaproctracker) · [Addon source](https://github.com/Gabbajoe/GabbaProcTracker)**

## How it works

1. Install GabbaProcTracker. Collect combat data, use `/reload` or log out (automatic export since addon 0.1.1; older versions need `/gpt export` first).
2. Install the companion for Windows, macOS or Linux.
3. Sign in on the website with Discord, GitHub or an email code. Create an upload token under Account for companion 0.1.2; existing pilot invitations still work.
4. Save the token in the app. Select characters; uploads are anonymous by default. Public character name and realm are an explicit per-character choice.
5. Enable automatic uploads if desired. Choose an upload interval from 5 to 60 minutes (default: 15). Closing the window keeps the app running in the tray; use Open or Quit in its menu, or Quit app in the window. If tray creation fails, closing quits the app. Start-at-login and signed automatic app updates are optional.

The app searches common Battle.net, Wine, Faugus and Steam prefixes. A manual WoW-folder picker handles other installations. Only `_classic_era_` character exports are considered. It never executes Lua. Use the preview to inspect the exact allowlisted JSON before uploading.

Upload tokens go into the OS keyring. If unavailable, the app retains the token only in memory until it quits. Preferences contain local folder paths and character UUIDs, but no upload token. App downloads and signed update artifacts are hosted on GitHub Releases.

On Linux, the app creates a user start-menu entry and icon. Starting an AppImage again after moving or renaming it refreshes that entry to its current path. After a signed in-app update, the AppImage is renamed to include its new version and the launcher is refreshed before restart. Existing files are never overwritten by this rename.

**Linux:** download the `.rpm` for Fedora, the `.deb` for Debian/Ubuntu, or the AppImage for a portable installation. Install the Fedora package with:

```sh
sudo dnf install ./GabbaProc.Companion-*.x86_64.rpm
```

Automatic updates support all three formats. Updating a system-installed RPM or DEB can ask for administrator authorization; an AppImage in your writable applications folder normally does not.

## What the numbers mean

Rates are **combat procs / eligible combat minutes**, aggregated by exposure, not the mean of character rates. They are not proc probabilities per hit. Attack speed, targets, class and equipment remain confounders. Locally editable data cannot be authenticated as genuine gameplay. The site labels it community data; extreme rates are quarantined for review.

The PostgreSQL server keeps the newest cumulative snapshot per character/collection and retains all completed combat segments it receives. Upload packets are bounded, but a later packet does not replace previously received history. Older addon versions provide only their rolling window; fights never exported or uploaded cannot be reconstructed. Re-importing does not add counts twice. Unknown/custom effects are omitted. UUIDs are pseudonyms, not authentication credentials.

The companion saves pending archive packets locally until the server confirms processing. Separate bars show received and processed packets. Tabs separate character selection, synchronization, account access and settings; optional bandwidth limits apply to uploads.

## Privacy and deletion

Anonymous uploads omit name, realm, zone, account/folder paths and raw SavedVariables. Public statistics omit UUIDs. Named contributors explicitly share their character name and realm. The app can hide a previously published name, or delete every collection owned by its token and revoke that token. Copies previously downloaded by others cannot be recalled.

Accounts support explicit linking of additional sign-in methods, device revocation and account deletion. Existing upload tokens can be attached after proving possession, preserving their character ownership. Account provider names and email addresses are never public contributor names. UUID knowledge alone cannot claim someone else's records. See [SECURITY.md](SECURITY.md).

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8757
cd desktop
cargo test --locked -p gabbaproc-core
npm ci
npm run tauri dev
```

The desktop archive queue requires the PostgreSQL API and worker; the simple server command above is for API/UI development. See [local companion testing](LOCAL-COMPANION-TEST.md) and [production operations](deploy/PRODUCTION.md) for complete setups.

Native app builds require Tauri's OS development dependencies (WebKitGTK 4.1/GTK 3 on Linux, Xcode tools on macOS, MSVC/WebView2 on Windows). `cargo test -p gabbaproc-core` does not require a GUI toolkit.

Releases are built in GitHub Actions for Windows, Linux, Apple Silicon and Intel Mac. Updater signatures are mandatory. They are separate from Windows Authenticode and Apple notarization: this initial release has neither of those platform identities, so OS warnings may occur. Never bypass a failed updater signature. See [RELEASING.md](RELEASING.md).

## Deutsch

Website und Companion sind deutsch/englisch. Die App sucht deinen WoW-Ordner, liest ausschließlich die Proc-Exporte und lädt nur gewählte Charaktere hoch. Automatischer Upload, Autostart und signierte Updates sind optional. Anonym heißt pseudonym: Die dauerhafte UUID erlaubt zusammenhängende Auswertungen. Charaktername und Realm werden nur auf ausdrücklichen Wunsch veröffentlicht.

Ein Export im Addon plus `/reload` oder Ausloggen schreibt die Datei auf die Festplatte. Die App kann nicht auf noch ungespeicherte Daten im WoW-Prozess zugreifen. Die Anmeldung funktioniert mit Discord, GitHub oder E-Mail-Code. Bestehende Einladungen bleiben gültig. Messwerte sind Community-Beiträge und kein Beweis für unterschiedliche Proc-Chancen.

### Account and companion controls

Choose a username on the account page; the website and connected companion display it beside the language selector. Browser sessions last up to 14 days. Companion access has no automatic expiry and can be disconnected or revoked without deleting contributions. Reconnecting the same device preserves ownership and its local upload queue.

Auto-upload, interval and bandwidth are in **Sync**. **Settings** contains autostart, updates and the option to minimize to the tray when closing (enabled by default). The tray reports connection and synchronization status, including the next automatic export check. Character previews open beneath the selected character. The bottom status bar stays visible across tabs. Click the logo/title to open the website, or the source link in the footer to open GitHub.

### Raid-test data and analysis (0.1.3)

Companion 0.1.3 imports addon export schemas 1 and 2. New segment telemetry is projected through an explicit allowlist; numeric equipment/talent context, available stat/buff samples, attack outcomes, relative proc times and target counts are retained. No raw combat log, item links, target GUIDs or target names are uploaded. Field limits are enforced again by the server. Legacy segments have no inferred telemetry.

[Combat analysis](https://gabbaproc.kellerkind.info/analysis.html) shows environment rates, duration groups, zero-proc proportions, count distribution, duration/proc scatter and relative timing histograms. Scope can be community or the signed-in account. The initial view scans at most 500 recent archived segments to bound server work; it is not an all-history aggregation. Rates use total eligible seconds, not averages of per-segment rates. Damage-event counts are not effect-specific trigger attempts. Timing summaries exclude truncated combat detail; sampled buffs do not establish exact uptime. Further controlled raid validation is required.

Language is configured under Settings: System language (English fallback), Deutsch or English. The header displays the connected account. Header/footer span the window width; the desktop window has a fixed 920 × 780 size.

### Manual browser uploads

Signed-in users can upload a character's SavedVariables file at `/upload.html`.
A dedicated worker runs the same Rust parser and allowlist projection as the
companion, compiled to WebAssembly. The original file never leaves the browser.
Uploads require an explicit confirmation after a pseudonymous/named preview and
use the existing bounded server queue, validation and import receipts.
Existing linked character ownership is retained; unrelated accounts cannot claim it.
The first companion paired after a browser-only upload inherits that upload identity.

Rebuild the committed browser parser after changing the Rust core:
`rustup target add wasm32-unknown-unknown`, then `bash tools/build-browser-parser.sh`.
The server CSP permits only same-origin workers and WebAssembly compilation
(`wasm-unsafe-eval`); it does not allow JavaScript `eval` or execution of uploaded Lua.
