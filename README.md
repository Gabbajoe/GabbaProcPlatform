# ⚡ GabbaProc Platform

![Checks](https://github.com/Gabbajoe/GabbaProcPlatform/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-gold)
![Languages](https://img.shields.io/badge/languages-English%20%2F%20Deutsch-teal)

Community proc research for WoW Classic Era / Hardcore. Website, API and lightweight Tauri companion, openly maintained in one repository.

**[Website](https://gabbaproc.kellerkind.info) · [Companion releases](https://github.com/Gabbajoe/GabbaProcPlatform/releases) · [Addon](https://github.com/Gabbajoe/GabbaProcTracker)**

## How it works

1. Install GabbaProcTracker. Collect combat data, use `/reload` or log out (automatic export since addon 0.1.1; older versions need `/gpt export` first).
2. Install the companion for Windows, macOS or Linux. It uses the operating system WebView, without shipping Chromium.
3. Get a single-use pilot invite from the operator and exchange it on the website for an upload token.
4. Save the token in the app. Select characters; uploads are anonymous by default. Public character name and realm are an explicit per-character choice.
5. Enable automatic uploads if desired. Changed exports upload every minute while the app is open. Closing the window quits the app. Start-at-login and signed automatic app updates are optional.

The app searches common Battle.net, Wine, Faugus and Steam prefixes. A manual WoW-folder picker handles other installations. Only `_classic_era_` character exports are considered. It never executes Lua. Use the preview to inspect the exact allowlisted JSON before uploading.

Upload tokens go into the OS keyring. If unavailable, the app retains the token only in memory until it quits. Preferences contain local folder paths and character UUIDs, but no upload token. App downloads and signed update artifacts are hosted on GitHub Releases.

**Linux:** use the **AppImage** for built-in automatic updates. The optional `.deb` is a smaller download that relies on installed system libraries and must be updated manually by installing a newer package. The initial `.deb` interface still shows the updater controls; those cannot install a Linux package update. [Upstream updater formats](https://v2.tauri.app/plugin/updater/#building).

## What the numbers mean

Rates are **combat procs / eligible combat minutes**, aggregated by exposure, not the mean of character rates. They are not proc probabilities per hit. Attack speed, targets, class and equipment remain confounders. Locally editable data cannot be authenticated as genuine gameplay. The site labels it community data; extreme rates are quarantined for review.

The server stores the newest cumulative snapshot for each character/collection and its rolling window of at most 301 combat segments. Re-importing does not add counts twice. Unknown/custom effects are omitted. UUIDs are pseudonyms, not authentication credentials.

## Privacy and deletion

Anonymous uploads omit name, realm, zone, account/folder paths and raw SavedVariables. Public statistics omit UUIDs. Named contributors explicitly share their character name and realm. The app can hide a previously published name, or delete every collection owned by its token and revoke that token. Copies previously downloaded by others cannot be recalled.

This first pilot uses operator-issued invites to limit abuse. Moving an existing character to another token requires operator intervention; UUID knowledge alone cannot claim someone else's records. See [SECURITY.md](SECURITY.md).

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

Native app builds require Tauri's OS development dependencies (WebKitGTK 4.1/GTK 3 on Linux, Xcode tools on macOS, MSVC/WebView2 on Windows). `cargo test -p gabbaproc-core` does not require a GUI toolkit.

Releases are built in GitHub Actions for Windows, Linux, Apple Silicon and Intel Mac. Updater signatures are mandatory. They are separate from Windows Authenticode and Apple notarization: this initial release has neither of those platform identities, so OS warnings may occur. Never bypass a failed updater signature. See [RELEASING.md](RELEASING.md).

## Deutsch

Website und Companion sind deutsch/englisch. Die App sucht deinen WoW-Ordner, liest ausschließlich die Proc-Exporte und lädt nur gewählte Charaktere hoch. Automatischer Upload, Autostart und signierte Updates sind optional. Anonym heißt pseudonym: Die dauerhafte UUID erlaubt zusammenhängende Auswertungen. Charaktername und Realm werden nur auf ausdrücklichen Wunsch veröffentlicht.

Ein Export im Addon plus `/reload` oder Ausloggen schreibt die Datei auf die Festplatte. Die App kann nicht auf noch ungespeicherte Daten im WoW-Prozess zugreifen. Die Sammlung ist zunächst ein einladungsbasierter Pilot. Messwerte sind Community-Beiträge und kein Beweis für unterschiedliche Proc-Chancen.
