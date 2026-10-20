#!/usr/bin/env bash
# Local development build only. Does not publish or invoke GitHub Actions.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
output="$repo/desktop/target/local-build"
mkdir -p "$output"/{target,cargo,cache}
cat > "$output/config.json" <<'JSON'
{"version":"0.1.2-dev.3","identifier":"info.kellerkind.gabbaproc.dev","bundle":{"createUpdaterArtifacts":false},"app":{"windows":[{"title":"GabbaProc Companion — Local development","width":920,"height":780,"minWidth":650,"minHeight":560}]}}
JSON
podman build -t localhost/gabbaproc-appimage-build -f "$repo/deploy/companion-build.Containerfile" "$repo/deploy"
podman run --rm --security-opt label=disable \
  -v "$repo/desktop:/work/desktop" -v "$repo/server:/work/server:ro" \
  -v "$output/target:/target" -v "$output/cargo:/cache" \
  -v "$output/cache:/root/.cache" -v "$output/config.json:/tmp/local-build.json:ro" \
  -e CARGO_HOME=/cache -e CARGO_TARGET_DIR=/target -e CARGO_BUILD_JOBS=4 \
  -e APPIMAGE_EXTRACT_AND_RUN=1 localhost/gabbaproc-appimage-build \
  sh -c 'npm ci && cargo test --locked -p gabbaproc-companion --lib && npm run tauri -- build --debug --bundles appimage --config /tmp/local-build.json'
cp "$output/target/debug/bundle/appimage/GabbaProc Companion_0.1.2-dev.3_amd64.AppImage" "$output/GabbaProc-Companion-0.1.2-dev.3-x86_64.AppImage"
(cd "$output" && sha256sum GabbaProc-Companion-0.1.2-dev.3-x86_64.AppImage > SHA256SUMS)
