# Releases

1. Run API and Rust core tests. Ensure the native desktop check is green.
2. Bump `desktop/src-tauri/tauri.conf.json`, both Cargo package versions and `desktop/package.json`; refresh lockfiles.
3. Tag `vX.Y.Z` and push. The release workflow builds all platforms into a **draft** release.
4. Check all four jobs and artifacts, then publish the draft. GitHub hosts installers and `latest.json`; the companion checks this manifest.

`TAURI_SIGNING_PRIVATE_KEY` must be a repository Actions secret. The matching public key is compiled into the app. Keep an offline private backup: loss of this key breaks seamless updates for installed clients. Never commit it. Rotation needs a carefully staged release. A signed updater artifact is not an Apple-notarized or Authenticode-signed installer.

No app package download passes through the community server. Backend deployments are separate, deliberate operator actions; pushing a website commit does not silently change the production database.

The pinned updater supports AppImage and native DEB updates; preserve the matching `linux-x86_64-appimage` and `linux-x86_64-deb` manifest entries. System DEB installation may prompt for administrator authorization. Keep all four OS/architecture entries in `latest.json`; verify each signature against the compiled public key before publishing the draft.

For independent verification, download all assets and run `python tools/verify_release.py /path/to/assets` with `minisign` installed. It requires all four OS/architecture targets, checks GitHub download origins, compares manifest/asset signatures, verifies every update payload with the compiled public key, and writes `SHA256SUMS.txt`.
